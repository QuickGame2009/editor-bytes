import os

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import logica

# --- Android: archivos (SAF) y NFC ---
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    from android import activity

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Activity = autoclass("android.app.Activity")
    JString = autoclass("java.lang.String")
    InputStreamReader = autoclass("java.io.InputStreamReader")
    BufferedReader = autoclass("java.io.BufferedReader")
    NfcAdapter = autoclass("android.nfc.NfcAdapter")
    MifareClassic = autoclass("android.nfc.tech.MifareClassic")
    ANDROID = True
except Exception:
    ANDROID = False

REQ_ABRIR = 1001
REQ_KEYS = 1002
REQ_GUARDAR = 1003

BITS_ORDEN = [78, 79, 82, 81, 80]
ESPERA_TARJETA = 10

TEMAS = {
    "oscuro": dict(
        fondo=(0.08, 0.08, 0.10, 1), texto=(0.92, 0.92, 0.92, 1),
        caja=(0.12, 0.12, 0.12, 1), caja_txt=(0.80, 1, 0.80, 1),
        in_bg=(0.20, 0.20, 0.23, 1), in_txt=(0.96, 0.96, 0.96, 1),
        ro_bg=(0.14, 0.14, 0.16, 1), ro_txt=(0.65, 0.75, 0.90, 1),
        rojo=(1, 0.45, 0.40, 1), verde=(0.45, 0.90, 0.50, 1)),
    "claro": dict(
        fondo=(0.95, 0.95, 0.96, 1), texto=(0.10, 0.10, 0.10, 1),
        caja=(1, 1, 1, 1), caja_txt=(0.05, 0.25, 0.05, 1),
        in_bg=(1, 1, 1, 1), in_txt=(0, 0, 0, 1),
        ro_bg=(0.88, 0.88, 0.90, 1), ro_txt=(0.20, 0.30, 0.55, 1),
        rojo=(0.80, 0.10, 0.05, 1), verde=(0.10, 0.50, 0.15, 1)),
}


if ANDROID:
    class _Lector(PythonJavaClass):
        __javainterfaces__ = ["android/nfc/NfcAdapter$ReaderCallback"]

        def __init__(self, callback):
            super().__init__()
            self._callback = callback

        @java_method("(Landroid/nfc/Tag;)V")
        def onTagDiscovered(self, tag):
            self._callback(tag)


class Almacen:
    """Abre y guarda archivos con el selector del sistema (Android SAF)."""

    def __init__(self):
        self.callbacks = {}
        self._contenido = None
        if ANDROID:
            activity.bind(on_activity_result=self._resultado)

    def _actividad(self):
        return cast("android.app.Activity", PythonActivity.mActivity)

    def abrir(self, request, callback):
        self.callbacks[request] = callback
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        self._actividad().startActivityForResult(intent, request)

    def guardar(self, contenido, nombre, callback):
        self.callbacks[REQ_GUARDAR] = callback
        self._contenido = contenido
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        intent.putExtra(Intent.EXTRA_TITLE, nombre)
        self._actividad().startActivityForResult(intent, REQ_GUARDAR)

    def _resultado(self, request, result, intent):
        cb = self.callbacks.pop(request, None)
        if result != Activity.RESULT_OK or intent is None or cb is None:
            return
        uri = intent.getData()
        resolver = self._actividad().getContentResolver()
        if request == REQ_GUARDAR:
            flujo = resolver.openOutputStream(uri)
            flujo.write(JString(self._contenido).getBytes("UTF-8"))
            flujo.flush()
            flujo.close()
            cb()
        else:
            flujo = resolver.openInputStream(uri)
            lector = BufferedReader(InputStreamReader(flujo, "UTF-8"))
            lineas = []
            linea = lector.readLine()
            while linea is not None:
                lineas.append(linea)
                linea = lector.readLine()
            lector.close()
            cb("\n".join(lineas))


class Interfaz(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12),
                         spacing=dp(6), **kwargs)
        self.almacen = Almacen()
        self.contenido = None
        self.nombre = "dump_mod.mct"
        self.tema = "oscuro"
        self.claves = []
        self.modo = None
        self.bloques_escribir = []
        self.tarjeta_vista = False
        self.cuenta = ESPERA_TARJETA
        self._ev_cuenta = None
        self.nfc_ok = self._nfc_disponible()

        self.labels = []
        self.inputs = []
        self.readonly = []
        self.checks = []

        # Cabecera
        cabecera = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        cabecera.add_widget(self._lbl("[b]Editor de dump .mct[/b]", dp(40),
                                      "18sp", markup=True))
        self.boton_tema = Button(text="Modo claro", size_hint_x=None,
                                 width=dp(118), font_size="14sp")
        self.boton_tema.bind(on_release=self._cambiar_tema)
        cabecera.add_widget(self.boton_tema)
        self.add_widget(cabecera)

        # Línea de estado NFC
        self.aviso = self._lbl("", dp(24), "14sp")
        self.add_widget(self.aviso)

        # Fila superior (botones según estado)
        self.fila_top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.add_widget(self.fila_top)
        self._actualizar_botones_top()

        self.estado = self._lbl("Ningún archivo abierto.", dp(26), "14sp")
        self.add_widget(self.estado)

        # --- Sector 1 ---
        self.add_widget(self._lbl("Sector 1 · 5º byte -> bloques 1 y 2 (0-127):",
                                  dp(24), "14sp"))
        self.sector1_ok = False
        fila = BoxLayout(size_hint_y=None, height=dp(70), spacing=dp(6))
        izq = BoxLayout(orientation="vertical")
        izq.add_widget(self._lbl("Original (dump)", dp(20), "12sp"))
        self.valor_orig = self._caja_ro()
        izq.add_widget(self.valor_orig)
        fila.add_widget(izq)
        fila.add_widget(self._lbl("->", dp(70), "20sp", ancho=dp(24)))
        der = BoxLayout(orientation="vertical")
        der.add_widget(self._lbl("Nuevo", dp(20), "12sp"))
        self.valor_byte4 = self._campo("0-127")
        der.add_widget(self.valor_byte4)
        fila.add_widget(der)
        self.add_widget(fila)

        # --- Sector 3 ---
        self.add_widget(self._lbl("Sector 3 · bloque 0 · bits 78-82:", dp(24), "14sp"))
        self.sector3_ok = False
        self.bits_cb = {}
        self.bits_orig = {}
        self.add_widget(self._fila_bits(self.bits_cb, editable=True))
        self.resumen_bits = self._lbl("Abre un dump para activar las casillas.",
                                      dp(22), "13sp")
        self.add_widget(self.resumen_bits)
        self.add_widget(self._lbl("Original (dump):", dp(20), "12sp"))
        self.add_widget(self._fila_bits(self.bits_orig, editable=False))

        # Fila inferior
        self.fila_bot = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        self.fila_bot.add_widget(self._boton("Guardar dump", self.guardar_dump, dp(54)))
        self.boton_escribir = self._boton("Escribir etiqueta", self.escribir, dp(54))
        self.add_widget(self.fila_bot)

        # Log desplazable
        self.log_scroll = ScrollView(size_hint_y=1)
        self.log = Label(text="", font_name="RobotoMono-Regular", font_size="13sp",
                         size_hint_y=None, halign="left", valign="top")
        self.log.bind(width=lambda *_: setattr(self.log, "text_size",
                                               (self.log.width, None)))
        self.log.bind(texture_size=lambda *_: setattr(self.log, "height",
                                                      self.log.texture_size[1]))
        self.log_scroll.add_widget(self.log)
        self.add_widget(self.log_scroll)

        self._aplicar_tema()

        if self.nfc_ok:
            self._set_aviso("buscando")
            self._ev_cuenta = Clock.schedule_interval(self._tick, 1)
        else:
            self._set_aviso("incompat")

        self._lector = _Lector(self._tag_detectada) if ANDROID and self.nfc_ok else None
        self.activar_lector()

        if os.environ.get("FORZAR_DETECTADA") == "1":
            self._marcar_detectada_sync()

    # --- fábricas ---
    def _lbl(self, texto, alto, fuente, markup=False, ancho=None):
        l = Label(text=texto, size_hint_y=None, height=alto, font_size=fuente,
                  markup=markup)
        if ancho is not None:
            l.size_hint_x = None
            l.width = ancho
        self.labels.append(l)
        return l

    def _boton(self, texto, cb, alto):
        b = Button(text=texto, size_hint_y=None, height=alto, font_size="15sp")
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
        for numero in BITS_ORDEN:
            celda = BoxLayout(orientation="vertical")
            celda.add_widget(self._lbl(f"bit {numero}", dp(20), "12sp"))
            cb = CheckBox(disabled=True)
            if editable:
                cb.bind(active=lambda *_: self._resumen_bits())
            destino[numero] = cb
            self.checks.append(cb)
            celda.add_widget(cb)
            fila.add_widget(celda)
        return fila

    def _actualizar_botones_top(self):
        self.fila_top.clear_widgets()
        if self.tarjeta_vista:
            self.fila_top.add_widget(self._boton("Ver .mct", self.ver_mct, dp(52)))
            self.fila_top.add_widget(self._boton("Cargar .keys", self.cargar_keys, dp(52)))
        elif self.contenido is not None:
            self.fila_top.add_widget(self._boton("Cambiar .mct", self.abrir, dp(52)))
            self.fila_top.add_widget(self._boton("Ver .mct", self.ver_mct, dp(52)))
        else:
            self.fila_top.add_widget(self._boton("Abrir .mct", self.abrir, dp(52)))

    # --- tema / aviso ---
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
        self.log.color = t["caja_txt"]
        self._color_aviso()

    def _set_aviso(self, estado):
        self.aviso_estado = estado
        if estado == "buscando":
            self.aviso.text = f"Buscando tarjeta MIFARE ({self.cuenta})"
        elif estado == "incompat":
            self.aviso.text = "Este móvil no es compatible con MIFARE Classic"
        elif estado == "no_detectada":
            self.aviso.text = "Tarjeta MIFARE Classic no detectada"
        elif estado == "archivo":
            self.aviso.text = "Dump .mct seleccionado"
        else:
            self.aviso.text = "Tarjeta MIFARE detectada"
        self._color_aviso()

    def _color_aviso(self):
        t = TEMAS[self.tema]
        estado = getattr(self, "aviso_estado", "buscando")
        if estado in ("incompat", "no_detectada"):
            self.aviso.color = t["rojo"]
        elif estado in ("detectada", "archivo"):
            self.aviso.color = t["verde"]
        else:
            self.aviso.color = t["texto"]

    def _tick(self, dt):
        if self.tarjeta_vista:
            return False
        self.cuenta -= 1
        if self.cuenta <= 0:
            self._set_aviso("no_detectada")
            return False
        self._set_aviso("buscando")
        return True

    # --- log ---
    def _set_log(self, texto):
        self.log.text = texto
        self.log_scroll.scroll_y = 1

    def _add_log(self, texto):
        self.log.text += texto
        self.log_scroll.scroll_y = 1

    # --- sector 3 ---
    def valor_bits_actual(self):
        valor = 0
        for numero, cb in self.bits_cb.items():
            if cb.active:
                valor |= (1 << (numero - 78))
        return valor

    def _resumen_bits(self):
        if not self.sector3_ok:
            return
        v = self.valor_bits_actual()
        self.resumen_bits.text = f"Valor = {v}  ({format(v, '05b')} binario)"

    def _cargar_estado(self):
        dump = logica.DumpMCT(self.contenido)
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
        b3 = dump.get_bloque(3, 0)
        if b3 is not None and b3.strip("-") != "":
            valor = logica.valor_bits_de_bloque(logica._bloque_a_bytes(b3))
            for numero, cb in self.bits_cb.items():
                cb.disabled = False
                cb.active = bool(valor & (1 << (numero - 78)))
            for numero, cb in self.bits_orig.items():
                cb.active = bool(valor & (1 << (numero - 78)))
            self.sector3_ok = True
            self._resumen_bits()
        else:
            self.sector3_ok = False
            for cb in list(self.bits_cb.values()) + list(self.bits_orig.values()):
                cb.active = False
                cb.disabled = True
            self.resumen_bits.text = "Sector 3, bloque 0 sin leer: no se puede editar."

    # --- archivos ---
    def abrir(self, *_):
        if ANDROID:
            self.almacen.abrir(REQ_ABRIR, self._archivo_abierto)
        else:
            self._leer_local("MCT_PATH", self._archivo_abierto)

    def cargar_keys(self, *_):
        if ANDROID:
            self.almacen.abrir(REQ_KEYS, self._keys_cargadas)
        else:
            self._leer_local("MCT_KEYS", self._keys_cargadas)

    def _leer_local(self, var, cb):
        ruta = os.environ.get(var, "")
        try:
            with open(ruta, encoding="utf-8") as f:
                cb(f.read())
            if var == "MCT_PATH":
                base = ruta.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                self.nombre = base + "_mod.mct"
        except OSError as e:
            self._set_log(f"No se pudo abrir: {e}")

    @mainthread
    def _archivo_abierto(self, contenido):
        self.contenido = contenido
        try:
            n = len(logica.DumpMCT(contenido).bloques)
            self.estado.text = f"Dump cargado ({n} bloques)."
            self._set_log("Dump cargado. Ajusta los valores.")
            self._cargar_estado()
            if not self.tarjeta_vista:
                if self._ev_cuenta:
                    self._ev_cuenta.cancel()
                    self._ev_cuenta = None
                self._set_aviso("archivo")
        except ValueError as e:
            self.contenido = None
            self.estado.text = "Archivo no válido."
            self._set_log(f"Error: {e}")
        self._actualizar_botones_top()

    @mainthread
    def _keys_cargadas(self, contenido):
        self.claves = logica.parse_keys(contenido)
        self.estado.text = f"{len(self.claves)} claves cargadas."

    def ver_mct(self, *_):
        if self.contenido is None:
            self._set_log("No hay dump que ver.")
            return
        t = TEMAS[self.tema]
        cont = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        editor = TextInput(text=self.contenido, font_name="RobotoMono-Regular",
                           font_size="13sp", background_color=t["caja"],
                           foreground_color=t["caja_txt"])
        cont.add_widget(editor)
        barra = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        b_guardar = Button(text="Guardar en archivo")
        b_cerrar = Button(text="Aplicar y cerrar")
        barra.add_widget(b_guardar)
        barra.add_widget(b_cerrar)
        cont.add_widget(barra)
        popup = Popup(title="Ver / editar .mct (hex)", content=cont,
                      size_hint=(0.96, 0.96))
        b_guardar.bind(on_release=lambda *_: self._guardar(editor.text, self._guardado))

        def cerrar(*_):
            try:
                logica.DumpMCT(editor.text)
                self.contenido = editor.text
                self._cargar_estado()
                self._set_log("Cambios del editor aplicados.")
            except ValueError as e:
                self._set_log(f"Texto no válido, no se aplicó: {e}")
            popup.dismiss()

        b_cerrar.bind(on_release=cerrar)
        popup.open()

    def _procesar(self):
        if self.contenido is None:
            self._set_log("Primero abre o importa un dump.")
            return None
        valor_bits = self.valor_bits_actual() if self.sector3_ok else None
        try:
            return logica.procesar_dump(self.contenido,
                                        valor_byte4=self.valor_byte4.text,
                                        valor_bits=valor_bits)
        except ValueError as e:
            self._set_log(f"Error: {e}")
            return None

    def _guardar(self, texto, cb):
        if ANDROID:
            self.almacen.guardar(texto, self.nombre, cb)
        else:
            destino = os.environ.get("MCT_OUT", "/tmp/salida_mod.mct")
            with open(destino, "w", encoding="utf-8") as f:
                f.write(texto)
            cb()

    def guardar_dump(self, *_):
        res = self._procesar()
        if res is None:
            return
        nuevo, log = res
        self._set_log(log)
        self._guardar(nuevo, self._guardado)

    @mainthread
    def _guardado(self):
        self._add_log("\n\nGuardado correctamente.")

    # --- NFC ---
    def _nfc_disponible(self):
        forzar = os.environ.get("FORZAR_NFC")
        if forzar in ("0", "1"):
            return forzar == "1"
        if not ANDROID:
            return False
        try:
            act = cast("android.app.Activity", PythonActivity.mActivity)
            adaptador = NfcAdapter.getDefaultAdapter(act)
            pm = act.getPackageManager()
            return adaptador is not None and pm.hasSystemFeature("com.nxp.mifare")
        except Exception:
            return False

    def activar_lector(self):
        if not (ANDROID and self.nfc_ok and self._lector):
            return
        try:
            act = cast("android.app.Activity", PythonActivity.mActivity)
            adaptador = NfcAdapter.getDefaultAdapter(act)
            flags = (NfcAdapter.FLAG_READER_NFC_A |
                     NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK)
            adaptador.enableReaderMode(act, self._lector, flags, None)
        except Exception:
            pass

    def desactivar_lector(self):
        if not (ANDROID and self.nfc_ok):
            return
        try:
            act = cast("android.app.Activity", PythonActivity.mActivity)
            NfcAdapter.getDefaultAdapter(act).disableReaderMode(act)
        except Exception:
            pass

    def escribir(self, *_):
        res = self._procesar()
        if res is None:
            return
        nuevo, log = res
        cambios = logica.diff_bloques(self.contenido, nuevo)
        if not cambios:
            self._set_log("No hay bloques modificados que escribir.")
            return
        self._nuevo_tras_escribir = nuevo
        self.bloques_escribir = cambios
        self.modo = "escribir"
        nums = ", ".join(str(logica.bloque_absoluto(s, i)) for s, i, _ in cambios)
        self._set_log(f"{log}\n\nAcerca la tarjeta para escribir los bloques {nums}.")

    def _claves_a_probar(self):
        return self.claves if self.claves else logica.CLAVES_DEFECTO

    def _tag_detectada(self, tag):
        self._marcar_detectada()
        try:
            mc = MifareClassic.get(tag)
            if mc is None:
                self._log("La tarjeta no es MIFARE Classic.")
                return
            mc.connect()
            try:
                if self.modo == "escribir":
                    self._escribir_tag(mc)
                elif self.contenido is None:
                    self._leer_tag(mc)
            finally:
                mc.close()
        except Exception as e:
            self._log(f"Error con la tarjeta: {e}")
        finally:
            self.modo = None

    def _auth(self, mc, sector):
        for clave in self._claves_a_probar():
            try:
                if mc.authenticateSectorWithKeyA(sector, clave):
                    return True
            except Exception:
                pass
        for clave in self._claves_a_probar():
            try:
                if mc.authenticateSectorWithKeyB(sector, clave):
                    return True
            except Exception:
                pass
        return False

    def _leer_tag(self, mc):
        bloques = {}
        leidos = 0
        for sector in range(logica.SECTORES):
            if self._auth(mc, sector):
                base = mc.sectorToBlock(sector)
                for indice in range(logica.BLOQUES_POR_SECTOR):
                    datos = mc.readBlock(base + indice)
                    bloques[(sector, indice)] = bytes((x & 0xFF) for x in datos).hex().upper()
                    leidos += 1
            else:
                for indice in range(logica.BLOQUES_POR_SECTOR):
                    bloques[(sector, indice)] = None
        self._dump_desde_tag(logica.construir_mct(bloques), leidos)

    def _escribir_tag(self, mc):
        ok, fallos = 0, []
        for sector, indice, hexs in self.bloques_escribir:
            if logica.es_trailer(indice):
                continue
            abs_b = logica.bloque_absoluto(sector, indice)
            if self._auth(mc, sector):
                try:
                    mc.writeBlock(abs_b, bytes.fromhex(hexs))
                    ok += 1
                except Exception:
                    fallos.append(abs_b)
            else:
                fallos.append(abs_b)
        self.contenido = self._nuevo_tras_escribir
        self._fin_escritura(ok, fallos)

    @mainthread
    def _marcar_detectada(self):
        self._marcar_detectada_sync()

    def _marcar_detectada_sync(self):
        self.tarjeta_vista = True
        if self._ev_cuenta:
            self._ev_cuenta.cancel()
            self._ev_cuenta = None
        self._set_aviso("detectada")
        if self.boton_escribir.parent is None:
            self.fila_bot.add_widget(self.boton_escribir)
        self._actualizar_botones_top()

    @mainthread
    def _dump_desde_tag(self, texto, leidos):
        self.contenido = texto
        self.nombre = "tarjeta_mod.mct"
        self.estado.text = f"Tarjeta leída ({leidos} bloques)."
        self._set_log("Tarjeta importada como dump. Ajusta los valores.")
        self._cargar_estado()
        self._actualizar_botones_top()

    @mainthread
    def _fin_escritura(self, ok, fallos):
        msg = f"Escritos {ok} bloques."
        if fallos:
            msg += f" Fallaron (sin clave o error): {', '.join(map(str, fallos))}."
        self._add_log("\n\n" + msg)
        self._cargar_estado()

    @mainthread
    def _log(self, texto):
        self._set_log(texto)


class EditorMctApp(App):
    title = "Editor de Bytes"

    def build(self):
        self.interfaz = Interfaz()
        return self.interfaz

    def on_resume(self):
        self.interfaz.activar_lector()
        return True

    def on_pause(self):
        self.interfaz.desactivar_lector()
        return True


if __name__ == "__main__":
    EditorMctApp().run()
