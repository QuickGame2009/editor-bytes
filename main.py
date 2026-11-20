from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout

import logica

KV = """
#:import dp kivy.metrics.dp

<Campo@TextInput>:
    multiline: False
    size_hint_y: None
    height: dp(48)
    font_size: '17sp'
    padding: dp(10), dp(12)

<Etiqueta@Label>:
    size_hint_y: None
    height: dp(28)
    font_size: '15sp'
    halign: 'left'
    text_size: self.size

<Boton@Button>:
    size_hint_y: None
    height: dp(52)
    font_size: '17sp'

<Herramienta>:
    orientation: 'vertical'
    padding: dp(14)
    spacing: dp(8)

    Etiqueta:
        text: 'Introduce los 16 bytes en hexadecimal:'
    Campo:
        id: hex
        hint_text: '00 11 22 33 ...'
    Etiqueta:
        text: root.texto_valor
    Campo:
        id: valor
        input_filter: 'int'
        input_type: 'number'
        hint_text: root.pista_valor
    BoxLayout:
        size_hint_y: None
        height: dp(52)
        spacing: dp(8)
        Boton:
            text: 'Calcular'
            on_release: root.calcular()
        Boton:
            text: 'Copiar'
            size_hint_x: 0.5
            on_release: root.copiar()
        Boton:
            text: 'Borrar'
            size_hint_x: 0.5
            on_release: root.borrar()
    TextInput:
        id: salida
        readonly: True
        font_name: 'RobotoMono-Regular'
        font_size: '15sp'
        background_color: 0.12, 0.12, 0.12, 1
        foreground_color: 0.9, 1, 0.9, 1

TabbedPanel:
    do_default_tab: False
    tab_width: self.width / 2
    tab_height: dp(50)
    TabbedPanelItem:
        text: 'Bits 78-82'
        Herramienta:
            texto_valor: 'Valor para los bits 78-82 (0-31):'
            pista_valor: '0-31'
            funcion: 'modificar_bits'
    TabbedPanelItem:
        text: 'Byte 4 + CRC'
        Herramienta:
            texto_valor: 'Valor decimal para el byte 4 (0-63):'
            pista_valor: '0-63'
            funcion: 'procesar_bloque'
"""


class Herramienta(BoxLayout):
    texto_valor = StringProperty("")
    pista_valor = StringProperty("")
    funcion = StringProperty("")

    def calcular(self):
        try:
            resultado = getattr(logica, self.funcion)(
                self.ids.hex.text, self.ids.valor.text
            )
        except ValueError as error:
            resultado = f"Error: {error}"
        self.ids.salida.text = resultado

    def copiar(self):
        # Copia la última línea del resultado (el bloque en hexadecimal continuo)
        lineas = [l for l in self.ids.salida.text.splitlines() if l.strip()]
        if lineas and not lineas[0].startswith("Error"):
            if self.funcion == "modificar_bits":
                Clipboard.copy(lineas[1])
            else:
                Clipboard.copy(lineas[-1])

    def borrar(self):
        self.ids.hex.text = ""
        self.ids.valor.text = ""
        self.ids.salida.text = ""


class EditorBytesApp(App):
    title = "Editor de Bytes"

    def build(self):
        return Builder.load_string(KV)


if __name__ == "__main__":
    EditorBytesApp().run()
