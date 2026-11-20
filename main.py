from kivy.app import App
from kivy.clock import mainthread
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import logica

# --- Acceso a archivos: SAF en Android, ruta a mano en escritorio ---
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


class Almacen:
    """Abre y guarda archivos usando el selector del sistema (Android SAF)."""

    def __init__(self):
        self.al_abrir = None
        self.al_guardar = None
        self._contenido_pendiente = None
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
        self._contenido_pendiente = contenido
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
            datos = JString(self._contenido_pendiente).getBytes("UTF-8")
            flujo.write(datos)
            flujo.flush()
            flujo.close()
            self.al_guardar()


class Interfaz(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(14),
                         spacing=dp(8), **kwargs)
        self.almacen = Almacen()
        self.contenido = None
        self.nombre = "dump_mod.mct"

        self.add_widget(Label(text="[b]Editor de dump .mct[/b]", markup=True,
                              size_hint_y=None, height=dp(34), font_size="19sp"))

        self.add_widget(self._boton("1 · Abrir .mct", self.abrir))

        self.estado = Label(text="Ningún archivo abierto.", size_hint_y=None,
                           height=dp(30), font_size="14sp")
        self.add_widget(self.estado)

        if not ANDROID:
            self.add_widget(Label(text="Ruta del .mct (solo escritorio):",
                                 size_hint_y=None, height=dp(24), halign="left"))
            self.ruta = TextInput(multiline=False, size_hint_y=None, height=dp(44),
                                 hint_text="/ruta/al/dump.mct")
            self.add_widget(self.ruta)

        self.add_widget(self._etiqueta("Sector 1 - byte 4 -> bloques 1 y 2 (0-63):"))
        self.valor_byte4 = self._campo("0-63")
        self.add_widget(self.valor_byte4)

        self.add_widget(self._etiqueta("Sector 3 - bloque 0 - bits 78-82 (0-31):"))
        self.valor_bits = self._campo("0-31")
        self.add_widget(self.valor_bits)

        self.add_widget(self._boton("2 · Aplicar y guardar", self.aplicar))

        scroll = ScrollView()
        self.salida = TextInput(readonly=True, font_name="RobotoMono-Regular",
                               font_size="14sp", size_hint_y=None,
                               background_color=(0.12, 0.12, 0.12, 1),
                               foreground_color=(0.85, 1, 0.85, 1))
        self.salida.bind(minimum_height=self.salida.setter("height"))
        self.salida.bind(text=lambda *_: setattr(
            self.salida, "height", max(dp(160), self.salida.minimum_height)))
        scroll.add_widget(self.salida)
        self.add_widget(scroll)

    # --- helpers de widgets ---
    def _boton(self, texto, cb):
        b = Button(text=texto, size_hint_y=None, height=dp(54), font_size="17sp")
        b.bind(on_release=cb)
        return b

    def _etiqueta(self, texto):
        return Label(text=texto, size_hint_y=None, height=dp(26),
                    font_size="14sp", halign="left",
                    text_size=(None, None))

    def _campo(self, pista):
        return TextInput(multiline=False, size_hint_y=None, height=dp(46),
                        input_filter="int", input_type="number",
                        hint_text=pista, font_size="17sp")

    # --- acciones ---
    def abrir(self, *_):
        if ANDROID:
            self.almacen.abrir(self._archivo_abierto)
        else:
            try:
                with open(self.ruta.text.strip(), encoding="utf-8") as f:
                    self._archivo_abierto(f.read())
                self.nombre = self.ruta.text.strip().rsplit("/", 1)[-1]
                self.nombre = self.nombre.rsplit(".", 1)[0] + "_mod.mct"
            except OSError as e:
                self.salida.text = f"No se pudo abrir: {e}"

    @mainthread
    def _archivo_abierto(self, contenido):
        self.contenido = contenido
        try:
            n = len(logica.DumpMCT(contenido).bloques)
            self.estado.text = f"Archivo cargado ({n} bloques)."
            self.salida.text = "Archivo .mct cargado. Introduce los valores y pulsa guardar."
        except ValueError as e:
            self.contenido = None
            self.estado.text = "Archivo no válido."
            self.salida.text = f"Error: {e}"

    def aplicar(self, *_):
        if self.contenido is None:
            self.salida.text = "Primero abre un archivo .mct."
            return
        try:
            nuevo, log = logica.procesar_dump(
                self.contenido,
                valor_byte4=self.valor_byte4.text,
                valor_bits=self.valor_bits.text,
            )
        except ValueError as e:
            self.salida.text = f"Error: {e}"
            return
        self.salida.text = log
        self._texto_a_guardar = nuevo
        if ANDROID:
            self.almacen.guardar(nuevo, self.nombre, self._guardado)
        else:
            destino = (self.ruta.text.strip().rsplit(".", 1)[0] or "dump") + "_mod.mct"
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
