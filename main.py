import os

from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

import logica

# --- Acceso a archivos: SAF en Android, variables de entorno en escritorio ---
try:
    from jnius import autoclass, cast
    from android import activity  # proporcionado por python-for-android

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Activity = autoclass("android.app.Activity")
    JString = autoclass("java.lang.String")
    InputStreamReader = autoclass("java.io.InputStreamReader")
    BufferedReader = autoclass("java.io.BufferedReader")
    ANDROID = True
except Exception:
    ANDROID = False

REQ_ABRIR = 1001
REQ_GUARDAR = 1002

TEMAS = {
    "oscuro": dict(
        fondo=(0.08, 0.08, 0.10, 1), texto=(0.92, 0.92, 0.92, 1),
        caja=(0.12, 0.12, 0.12, 1), caja_txt=(0.80, 1, 0.80, 1),
        in_bg=(0.20, 0.20, 0.23, 1), in_txt=(0.96, 0.96, 0.96, 1),
        ro_bg=(0.14, 0.14, 0.16, 1), ro_txt=(0.65, 0.75, 0.90, 1)),
    "claro": dict(
        fondo=(0.95, 0.95, 0.96, 1), texto=(0.10, 0.10, 0.10, 1),
        caja=(1, 1, 1, 1), caja_txt=(0.05, 0.25, 0.05, 1),
        in_bg=(1, 1, 1, 1), in_txt=(0, 0, 0, 1),
        ro_bg=(0.88, 0.88, 0.90, 1), ro_txt=(0.20, 0.30, 0.55, 1)),
}


class Almacen:
    """Abre y guarda archivos con el selector del sistema (Android SAF)."""

    def __init__(self):
        self.al_abrir = None
        self.al_guardar = None
        self._contenido = None
        if ANDROID:
            activity.bind(on_activity_result=self._resultado)

    def _actividad(self):
        return cast("android.app.Activity", PythonActivity.mActivity)

    def abrir(self, callback):
        self.al_abrir = callback
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        self._actividad().startActivityForResult(intent, REQ_ABRIR)

    def guardar(self, contenido, nombre, callback):
        self.al_guardar = callback
        self._contenido = contenido
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        intent.putExtra(Intent.EXTRA_TITLE, nombre)
        self._actividad().startActivityForResult(intent, REQ_GUARDAR)

    def _resultado(self, request, result, intent):
        if result != Activity.RESULT_OK or intent is None:
            return
        uri = intent.getData()
        resolver = self._actividad().getContentResolver()
        if request == REQ_ABRIR and self.al_abrir:
            flujo = resolver.openInputStream(uri)
            lector = BufferedReader(InputStreamReader(flujo, "UTF-8"))
            lineas = []
            linea = lector.readLine()
            while linea is not None:
                lineas.append(linea)
                linea = lector.readLine()
            lector.close()
            self.al_abrir("\n".join(lineas))
        elif request == REQ_GUARDAR and self.al_guardar:
            flujo = resolver.openOutputStream(uri)
            flujo.write(JString(self._contenido).getBytes("UTF-8"))
            flujo.flush()
            flujo.close()
            self.al_guardar()


class Interfaz(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12),
                         spacing=dp(6), **kwargs)
        self.almacen = Almacen()
        self.contenido = None
        self.nombre = "dump_mod.mct"
        self.tema = "oscuro"

        self.labels = []
        self.inputs = []       # editables
        self.readonly = []     # solo lectura
        self.checks = []

        # Cabecera: título + botón de modo nocturno
        cabecera = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        cabecera.add_widget(self._lbl("[b]Editor de dump .mct[/b]", dp(40),
                                      "19sp", markup=True))
        self.boton_tema = Button(text="Modo claro", size_hint_x=None,
                                 width=dp(120), font_size="14sp")
        self.boton_tema.bind(on_release=self._cambiar_tema)
        cabecera.add_widget(self.boton_tema)
        self.add_widget(cabecera)

        self.add_widget(self._boton("1 · Abrir .mct", self.abrir))
        self.estado = self._lbl("Ningún archivo abierto.", dp(28), "14sp")
        self.add_widget(self.estado)

        # --- Sector 1: valor original (solo lectura) -> valor nuevo ---
        self.add_widget(self._lbl("Sector 1 · 5º byte -> bloques 1 y 2 (0-127):",
                                  dp(24), "14sp"))
        self.sector1_ok = False
        fila = BoxLayout(size_hint_y=None, height=dp(72), spacing=dp(6))
        izq = BoxLayout(orientation="vertical")
        izq.add_widget(self._lbl("Original (dump)", dp(20), "12sp"))
        self.valor_orig = self._caja_ro()
        izq.add_widget(self.valor_orig)
        fila.add_widget(izq)
        fila.add_widget(self._lbl("->", dp(72), "20sp", ancho=dp(24)))
        der = BoxLayout(orientation="vertical")
        der.add_widget(self._lbl("Nuevo", dp(20), "12sp"))
        self.valor_byte4 = self._campo("0-127")
        der.add_widget(self.valor_byte4)
        fila.add_widget(der)
        self.add_widget(fila)

        # --- Sector 3: casillas editables + original en solo lectura ---
        self.add_widget(self._lbl("Sector 3 · bloque 0 · 5 bits:", dp(24), "14sp"))
        self.sector3_ok = False
        self.bits_cb = []      # editables (nuevo)
        self.bits_orig = []    # solo lectura (original)
        self.add_widget(self._fila_bits(self.bits_cb, editable=True))
        self.resumen_bits = self._lbl("Abre un dump para activar las casillas.",
                                      dp(22), "13sp")
        self.add_widget(self.resumen_bits)
        self.add_widget(self._lbl("Original (dump):", dp(20), "12sp"))
        self.add_widget(self._fila_bits(self.bits_orig, editable=False))

        self.add_widget(self._boton("2 · Aplicar y guardar", self.aplicar))

        # --- Log: caja fija, solo se desplaza el texto ---
        self.salida = TextInput(readonly=True, font_name="RobotoMono-Regular",
                                font_size="13sp", size_hint_y=1)
        self.add_widget(self.salida)

        self._aplicar_tema()

    # --- fábricas de widgets ---
    def _lbl(self, texto, alto, fuente, markup=False, ancho=None):
        l = Label(text=texto, size_hint_y=None, height=alto, font_size=fuente,
                  markup=markup)
        if ancho is not None:
            l.size_hint_x = None
            l.width = ancho
        self.labels.append(l)
        return l

    def _boton(self, texto, cb):
        b = Button(text=texto, size_hint_y=None, height=dp(52), font_size="17sp")
        b.bind(on_release=cb)
        return b

    def _campo(self, pista):
        t = TextInput(multiline=False, size_hint_y=None, height=dp(46),
                      input_filter="int", input_type="number",
                      hint_text=pista, font_size="18sp")
        self.inputs.append(t)
        return t

    def _caja_ro(self):
        t = TextInput(multiline=False, readonly=True, size_hint_y=None,
                      height=dp(46), hint_text="--", font_size="18sp")
        self.readonly.append(t)
        return t

    def _fila_bits(self, destino, editable):
        fila = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(4))
        for numero in range(1, 6):
            celda = BoxLayout(orientation="vertical")
            celda.add_widget(self._lbl(f"bit {numero}", dp(20), "12sp"))
            cb = CheckBox(disabled=True)
            if editable:
                cb.bind(active=lambda *_: self._resumen_bits())
            destino.append(cb)
            self.checks.append(cb)
            celda.add_widget(cb)
            fila.add_widget(celda)
        return fila

    # --- tema ---
    def _cambiar_tema(self, *_):
        self.tema = "claro" if self.tema == "oscuro" else "oscuro"
        self._aplicar_tema()

    def _aplicar_tema(self):
        t = TEMAS[self.tema]
        Window.clearcolor = t["fondo"]
        self.boton_tema.text = "Modo claro" if self.tema == "oscuro" else "Modo oscuro"
        for l in self.labels:
            l.color = t["texto"]
        for inp in self.inputs:
            inp.background_color = t["in_bg"]
            inp.foreground_color = t["in_txt"]
            inp.hint_text_color = (0.5, 0.5, 0.5, 1)
        for ro in self.readonly:
            ro.background_color = t["ro_bg"]
            ro.foreground_color = t["ro_txt"]
        for cb in self.checks:
            cb.color = t["texto"]
        self.salida.background_color = t["caja"]
        self.salida.foreground_color = t["caja_txt"]

    # --- sector 3 ---
    def valor_bits_actual(self):
        valor = 0
        for i, cb in enumerate(self.bits_cb):
            if cb.active:
                valor |= (16 >> i)
        return valor

    def _resumen_bits(self):
        if not self.sector3_ok:
            return
        v = self.valor_bits_actual()
        self.resumen_bits.text = f"Valor = {v}  ({format(v, '05b')} binario)"

    def _cargar_estado(self):
        dump = logica.DumpMCT(self.contenido)
        # Sector 1, bloque 1 -> valor del 5º byte
        b1 = dump.get_bloque(1, 1)
        if b1 is not None and b1.strip("-") != "":
            valor = logica._bloque_a_bytes(b1)[logica.IDX_VALOR]
            self.valor_orig.text = str(valor)
            self.valor_byte4.text = str(valor)
            self.sector1_ok = True
        else:
            self.valor_orig.text = "sin leer"
            self.valor_byte4.text = ""
            self.sector1_ok = False
        # Sector 3, bloque 0 -> 5 bits
        b3 = dump.get_bloque(3, 0)
        if b3 is not None and b3.strip("-") != "":
            valor = logica.valor_bits_de_bloque(logica._bloque_a_bytes(b3))
            for i, cb in enumerate(self.bits_cb):
                cb.disabled = False
                cb.active = bool((valor >> (4 - i)) & 1)
            for i, cb in enumerate(self.bits_orig):
                cb.active = bool((valor >> (4 - i)) & 1)
            self.sector3_ok = True
            self._resumen_bits()
        else:
            self.sector3_ok = False
            for cb in self.bits_cb + self.bits_orig:
                cb.active = False
                cb.disabled = True
            self.resumen_bits.text = "Sector 3, bloque 0 sin leer: no se puede editar."

    # --- acciones ---
    def abrir(self, *_):
        if ANDROID:
            self.almacen.abrir(self._archivo_abierto)
        else:
            ruta = os.environ.get("MCT_PATH", "")
            try:
                with open(ruta, encoding="utf-8") as f:
                    self._archivo_abierto(f.read())
                base = ruta.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                self.nombre = base + "_mod.mct"
            except OSError as e:
                self.salida.text = f"No se pudo abrir: {e}"

    @mainthread
    def _archivo_abierto(self, contenido):
        self.contenido = contenido
        try:
            n = len(logica.DumpMCT(contenido).bloques)
            self.estado.text = f"Archivo cargado ({n} bloques)."
            self.salida.text = "Archivo .mct cargado. Ajusta los valores y pulsa guardar."
            self._cargar_estado()
        except ValueError as e:
            self.contenido = None
            self.estado.text = "Archivo no válido."
            self.salida.text = f"Error: {e}"

    def aplicar(self, *_):
        if self.contenido is None:
            self.salida.text = "Primero abre un archivo .mct."
            return
        valor_bits = self.valor_bits_actual() if self.sector3_ok else None
        try:
            nuevo, log = logica.procesar_dump(
                self.contenido,
                valor_byte4=self.valor_byte4.text,
                valor_bits=valor_bits,
            )
        except ValueError as e:
            self.salida.text = f"Error: {e}"
            return
        self.salida.text = log
        if ANDROID:
            self.almacen.guardar(nuevo, self.nombre, self._guardado)
        else:
            destino = os.environ.get("MCT_OUT", "/tmp/salida_mod.mct")
            with open(destino, "w", encoding="utf-8") as f:
                f.write(nuevo)
            self.salida.text += f"\n\nGuardado en: {destino}"

    @mainthread
    def _guardado(self):
        self.salida.text += "\n\nArchivo guardado correctamente."


class EditorMctApp(App):
    title = "Editor de Bytes"

    def build(self):
        return Interfaz()


if __name__ == "__main__":
    EditorMctApp().run()
