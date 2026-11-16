import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val localProperties = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "com.arkaxhermes.app"
    compileSdk = 35

    // Chrome for Testing dibawa sebagai install-time asset pack (±128 MB).
    assetPacks += ":browser_pack"

    defaultConfig {
        applicationId = "com.arkaxhermes.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "ARKAX_UPSTREAM_TAG", "\"v0.23.1\"")
        buildConfigField("String", "ARKAX_ROOTFS", "\"ubuntu-24.04.5\"")
    }

    signingConfigs {
        if (localProperties.getProperty("ARKAX_STORE_FILE") != null) {
            create("arkaxRelease") {
                storeFile = file(localProperties.getProperty("ARKAX_STORE_FILE")!!)
                storePassword = localProperties.getProperty("ARKAX_STORE_PASSWORD")
                keyAlias = localProperties.getProperty("ARKAX_KEY_ALIAS")
                keyPassword = localProperties.getProperty("ARKAX_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            isDebuggable = true
            applicationIdSuffix = ".debug"
        }
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("arkaxRelease") ?: signingConfigs.getByName("debug")
        }
    }

    // Arsip rootfs sudah ter-gzip; kompresi ulang oleh aapt hanya memboroskan CPU.
    androidResources {
        listOf("gz", "tgz", "part", "tar", "xz", "zip", "so", "bin", "jsonl", "db")
            .forEach { noCompress += it }
    }

    packaging {
        // libproot.so harus benar-benar ada di nativeLibraryDir agar bisa dieksekusi.
        jniLibs { useLegacyPackaging = true }
        resources { setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*").forEach { excludes += it } }
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}

