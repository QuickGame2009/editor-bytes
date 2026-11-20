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


IDX_VALOR = 4   # índice 0-based donde se escribe el valor (5º byte del bloque)


def aplicar_byte4(bloque_bytes, valor):
    """Escribe el valor (0-63) en el 5º byte y el CRC plegado en el byte 16."""
    b = bytearray(bloque_bytes)
    b[IDX_VALOR] = valor
    crc16 = calcular_crc16(b[:15])
    crc_byte = (crc16 & 0xFF) ^ ((crc16 >> 8) & 0xFF)
    b[15] = crc_byte
    return b, crc16, crc_byte


# Campo de 5 bits, little-endian por bit: bit 78 = LSB (vale 1), bit 82 = MSB (vale 16).
# Cada bit del valor -> (byte del bloque, bit dentro del byte; bit 0 = 0x01).
#   valor bit 0 (bit 78) -> byte 9,  bit 5  (0x20)
#   valor bit 1 (bit 79) -> byte 9,  bit 6  (0x40)
#   valor bit 2 (bit 80) -> byte 9,  bit 7  (0x80)
#   valor bit 3 (bit 81) -> byte 10, bit 0  (0x01)
#   valor bit 4 (bit 82) -> byte 10, bit 1  (0x02)
MAPEO_BITS = [(9, 5), (9, 6), (9, 7), (10, 0), (10, 1)]


def valor_bits_de_bloque(bloque_bytes):
    """Devuelve el valor actual (0-31) del campo de 5 bits (bits 78-82)."""
    valor = 0
    for i, (by, bit) in enumerate(MAPEO_BITS):
        if bloque_bytes[by] & (1 << bit):
            valor |= (1 << i)
    return valor


def aplicar_bits(bloque_bytes, valor):
    """Escribe el valor (0-31) en el campo de 5 bits (bits 78-82)."""
    b = bytearray(bloque_bytes)
    for i, (by, bit) in enumerate(MAPEO_BITS):
        if (valor >> i) & 1:
            b[by] |= (1 << bit)
        else:
            b[by] &= ~(1 << bit)
    return b


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
        valor = leer_entero(valor_byte4, 0, 127)
        origen = _exigir_bloque(dump, 1, 1)
        nuevo, crc16, crc_byte = aplicar_byte4(origen, valor)
        hexs = nuevo.hex().upper()
        dump.set_bloque(1, 1, hexs)
        dump.set_bloque(1, 2, hexs)
        log.append("== Sector 1 · 5º byte + CRC ==")
        log.append(f"Valor: {valor} decimal = 0x{valor:02X} (5º byte)")
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


# ---------- MIFARE Classic 1K: claves, bloques y volcados ----------

SECTORES = 16
BLOQUES_POR_SECTOR = 4

# Claves por defecto que se prueban si no se carga un .keys.
CLAVES_DEFECTO = [
    bytes.fromhex(k) for k in (
        "FFFFFFFFFFFF", "A0A1A2A3A4A5", "D3F7D3F7D3F7", "000000000000",
        "B0B1B2B3B4B5", "4D3A99C351DD", "1A982C7E459A", "AABBCCDDEEFF",
    )
]


def parse_keys(texto):
    """Lee un .keys (MIFARE Classic Tool): una clave hex de 12 dígitos por línea."""
    claves = []
    vistas = set()
    for linea in texto.splitlines():
        l = linea.strip().replace(" ", "")
        if not l or l.startswith("#"):
            continue
        if len(l) == 12 and re.fullmatch(r"[0-9A-Fa-f]{12}", l):
            k = bytes.fromhex(l)
            if k not in vistas:
                vistas.add(k)
                claves.append(k)
    return claves


def bloque_absoluto(sector, indice):
    """Número de bloque absoluto en una tarjeta de 1K."""
    return sector * BLOQUES_POR_SECTOR + indice


def es_trailer(indice):
    """El último bloque de cada sector (claves y bits de acceso)."""
    return indice == BLOQUES_POR_SECTOR - 1


def diff_bloques(orig_texto, nuevo_texto):
    """Bloques que cambian entre dos volcados: lista de (sector, indice, hex)."""
    o = DumpMCT(orig_texto)
    n = DumpMCT(nuevo_texto)
    cambios = []
    for (sector, indice) in sorted(n.bloques):
        bo = o.get_bloque(sector, indice)
        bn = n.get_bloque(sector, indice)
        if bn is not None and es_hex32(bn) and bo != bn:
            cambios.append((sector, indice, bn))
    return cambios


def construir_mct(bloques):
    """Crea el texto de un .mct desde {(sector, indice): hex o None}."""
    lineas = []
    for sector in range(SECTORES):
        lineas.append(f"+Sector: {sector}")
        for indice in range(BLOQUES_POR_SECTOR):
            hexs = bloques.get((sector, indice))
            lineas.append(hexs.upper() if hexs else DESCONOCIDO)
    return "\n".join(lineas)
