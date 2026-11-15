# Arkaxhermes — WebView + JavascriptInterface harus dipertahankan.
-keepclassmembers class com.arkaxhermes.app.bridge.ArkaxJsBridge {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface
-keepattributes *Annotation*
-dontwarn java.nio.file.**
