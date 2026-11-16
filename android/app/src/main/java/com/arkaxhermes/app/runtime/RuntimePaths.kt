package com.arkaxhermes.app.runtime

import android.content.Context
import java.io.File

/** Semua lokasi filesystem yang dipakai Arkaxhermes. */
object RuntimePaths {
    const val HERMES_HOME_IN_ROOTFS = "/root/.hermes"
    const val SHARED_IN_ROOTFS = "/mnt/arkax"
    const val RUNTIME_IN_ROOTFS = "/opt/arkax"

    fun base(context: Context): File = File(context.filesDir, "arkax")
    fun rootfs(context: Context): File = File(base(context), "rootfs/ubuntu")
    fun rootfsArchive(context: Context): File = File(base(context), "rootfs.tar.gz")
    fun scripts(context: Context): File = File(base(context), "runtime")
    fun shared(context: Context): File = File(base(context), "shared")
    fun inbox(context: Context): File = File(shared(context), "inbox")
    fun exports(context: Context): File = File(shared(context), "exports")
    fun userScripts(context: Context): File = File(shared(context), "scripts")
    fun browser(context: Context): File = File(base(context), "browser")
    fun browserZip(context: Context): File = File(browser(context), "chrome-headless-shell.zip")
    fun browserChrome(context: Context): File = File(browser(context), "chrome")
    fun nativeDir(context: Context): String = context.applicationInfo.nativeLibraryDir
    fun tmp(context: Context): File = File(base(context), "tmp")
    fun installLog(context: Context): File = File(base(context), "install.log")
    fun readyMarker(context: Context): File = File(rootfs(context), ".arkax-ready")
    fun hermesHomeOnHost(context: Context): File = File(rootfs(context), "root/.hermes")

    /** proot HARUS berada di nativeLibraryDir (Android 10+ melarang exec dari filesDir). */
    fun prootBinary(context: Context): String =
        File(context.applicationInfo.nativeLibraryDir, "libproot.so").absolutePath

    fun prootLoader(context: Context): String? {
        val f = File(context.applicationInfo.nativeLibraryDir, "libproot-loader.so")
        return if (f.exists()) f.absolutePath else null
    }

    fun ensure(context: Context) {
        listOf(base(context), rootfs(context).parentFile!!, scripts(context), shared(context),
            inbox(context), exports(context), userScripts(context), tmp(context),
            browser(context), browserChrome(context))
            .forEach { if (!it.exists()) it.mkdirs() }
    }
}
