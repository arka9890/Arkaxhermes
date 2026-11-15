// Arkaxhermes — root build file.
// Versi plugin bisa dinaikkan mengikuti Android Studio Anda; kode sumber tidak
// bergantung pada API AGP yang spesifik.
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
