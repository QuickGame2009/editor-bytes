"""Lógica para editar un dump .mct (MIFARE Classic Tool), sin interfaz.

Operaciones:
 - byte 4 + CRC  -> sector 1, bloques 1 y 2 (el mismo resultado en ambos)
 - bits 78-82    -> sector 3, bloque 0
"""

import re

DESCONOCIDO = "-" * 32


# ---------- Utilidades de bloque ----------

def es_hex32(texto):
    return len(texto) == 32 and re.fullmatch(r"[0-9A-Fa-f]{32}", texto) is not None


def _bloque_a_bytes(hexs):
    if not es_hex32(hexs):
        raise ValueError("el bloque no contiene 16 bytes hexadecimales válidos.")
    return bytearray.fromhex(hexs)


def leer_entero(texto, minimo, maximo):
    try:
        valor = int(str(texto).strip())
    except (ValueError, TypeError):
        raise ValueError("introduce un número decimal válido.")
    if not minimo <= valor <= maximo:
        raise ValueError(f"el valor debe estar entre {minimo} y {maximo}.")
    return valor


# ---------- CRC y operaciones ----------

def calcular_crc16(datos):
    crc = 0xFFFF
    for byte in datos:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc & 0xFFFF


def aplicar_byte4(bloque_bytes, valor):
    """Escribe el valor (0-63) en el byte 4 y el CRC plegado en el byte 16."""
    b = bytearray(bloque_bytes)
    b[3] = valor
    crc16 = calcular_crc16(b[:15])
    crc_byte = (crc16 & 0xFF) ^ ((crc16 >> 8) & 0xFF)
    b[15] = crc_byte
    return b, crc16, crc_byte


def aplicar_bits(bloque_bytes, valor):
    """Escribe el valor (0-31) en los bits 78-82 del bloque de 128 bits."""
    numero = int.from_bytes(bloque_bytes, byteorder="big")
    desplazamiento = 128 - 82
    mascara = 0b11111 << desplazamiento
    numero = (numero & ~mascara) | (valor << desplazamiento)
    return bytearray(numero.to_bytes(16, byteorder="big"))


# ---------- Parseo del dump .mct ----------

class DumpMCT:
    """Carga un dump MCT preservando su estructura para reescribirlo igual."""

    def __init__(self, texto):
        self.lineas = texto.split("\n")
        self.bloques = {}  # (sector, indice_de_bloque) -> nº de línea
        sector = None
        indice = 0
        for i, linea in enumerate(self.lineas):
            l = linea.strip()
            if not l:
                continue
            if l.startswith("+"):
                m = re.search(r"(\d+)", l)
                sector = int(m.group(1)) if m else None
                indice = 0
                continue
            if sector is not None:
                self.bloques[(sector, indice)] = i
                indice += 1
        if not self.bloques:
            raise ValueError("el archivo no parece un dump .mct válido (sin sectores).")

    def get_bloque(self, sector, indice):
        i = self.bloques.get((sector, indice))
        if i is None:
            return None
        return self.lineas[i].strip()

    def set_bloque(self, sector, indice, hex32):
        self.lineas[self.bloques[(sector, indice)]] = hex32

    def texto(self):
        return "\n".join(self.lineas)


def _exigir_bloque(dump, sector, indice):
    bloque = dump.get_bloque(sector, indice)
    if bloque is None:
        raise ValueError(f"el dump no tiene el sector {sector}, bloque {indice}.")
    if bloque.strip("-") == "":
        raise ValueError(
            f"el sector {sector}, bloque {indice} está sin leer (----); "
            "hace falta el dump con ese bloque descifrado."
        )
    return _bloque_a_bytes(bloque)


# ---------- Proceso completo ----------

def procesar_dump(texto, valor_byte4=None, valor_bits=None):
    """Aplica las operaciones indicadas y devuelve (texto_modificado, registro).

    valor_byte4 y valor_bits pueden ser None (no tocar) o un texto/numero.
    """
    dump = DumpMCT(texto)
    log = []

    if valor_byte4 is not None and str(valor_byte4).strip() != "":
        valor = leer_entero(valor_byte4, 0, 63)
        origen = _exigir_bloque(dump, 1, 1)
        nuevo, crc16, crc_byte = aplicar_byte4(origen, valor)
        hexs = nuevo.hex().upper()
        dump.set_bloque(1, 1, hexs)
        dump.set_bloque(1, 2, hexs)
        log.append("== Sector 1 · byte 4 + CRC ==")
        log.append(f"Byte 4: {valor} decimal = 0x{valor:02X}")
        log.append(f"CRC16: 0x{crc16:04X}   CRC plegado: 0x{crc_byte:02X}")
        log.append("Escrito en sector 1, bloques 1 y 2:")
        log.append(" ".join(f"{b:02X}" for b in nuevo))

    if valor_bits is not None and str(valor_bits).strip() != "":
        valor = leer_entero(valor_bits, 0, 31)
        origen = _exigir_bloque(dump, 3, 0)
        nuevo = aplicar_bits(origen, valor)
        dump.set_bloque(3, 0, nuevo.hex().upper())
        if log:
            log.append("")
        log.append("== Sector 3 · bloque 0 · bits 78-82 ==")
        log.append(f"Valor: {valor} = {format(valor, '05b')} binario")
        log.append("Escrito en sector 3, bloque 0:")
        log.append(" ".join(f"{b:02X}" for b in nuevo))

    if not log:
        raise ValueError("no has introducido ningún valor para modificar.")

    return dump.texto(), "\n".join(log)
