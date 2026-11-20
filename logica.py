"""Lógica de los dos scripts, sin input() ni print(), para usarla desde la app."""


def leer_bloque(texto):
    """Convierte el texto hexadecimal en 16 bytes. Lanza ValueError si no es válido."""
    limpio = texto.replace(" ", "").replace(",", "").replace("\n", "").strip()
    try:
        bloque = bytearray.fromhex(limpio)
    except ValueError:
        raise ValueError("Hexadecimal no válido.")
    if len(bloque) != 16:
        raise ValueError(f"Se necesitan 16 bytes, has introducido {len(bloque)}.")
    return bloque


def leer_entero(texto, minimo, maximo):
    try:
        valor = int(texto.strip())
    except ValueError:
        raise ValueError("Introduce un número decimal válido.")
    if not minimo <= valor <= maximo:
        raise ValueError(f"El valor debe estar entre {minimo} y {maximo}.")
    return valor


# ---------- Script 1: modificar bits 78-82 ----------

def modificar_bits(texto_hex, texto_valor):
    datos = leer_bloque(texto_hex)
    valor = leer_entero(texto_valor, 0, 31)

    # Bits numerados desde 1 empezando por el más significativo
    numero = int.from_bytes(datos, byteorder="big")
    desplazamiento = 128 - 82
    mascara = 0b11111 << desplazamiento
    numero = (numero & ~mascara) | (valor << desplazamiento)
    resultado = numero.to_bytes(16, byteorder="big")

    return (
        "Resultado:\n"
        f"{resultado.hex().upper()}\n\n"
        "Valor introducido en binario:\n"
        f"{format(valor, '05b')}"
    )


# ---------- Script 2: byte 4 + CRC ----------

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


def procesar_bloque(texto_hex, texto_valor):
    bloque = leer_bloque(texto_hex)
    original = " ".join(f"{b:02X}" for b in bloque)
    valor = leer_entero(texto_valor, 0, 63)

    bloque[3] = valor
    crc16 = calcular_crc16(bloque[:15])
    crc_byte = (crc16 & 0xFF) ^ ((crc16 >> 8) & 0xFF)
    bloque[15] = crc_byte

    return (
        f"Bloque original:\n{original}\n\n"
        f"Byte 4 actualizado: {valor} decimal = 0x{valor:02X}\n\n"
        f"CRC16 calculado: 0x{crc16:04X}\n"
        f"CRC plegado:     0x{crc_byte:02X}\n\n"
        f"Bloque final:\n{' '.join(f'{b:02X}' for b in bloque)}\n\n"
        f"Bloque hexadecimal continuo:\n{bloque.hex().upper()}"
    )
