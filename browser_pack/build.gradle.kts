plugins {
    id("com.android.asset-pack")
}

assetPack {
    packName = "browser_pack"
    dynamicDelivery {
        // Install-time: Chrome for Testing ikut terpasang saat APK/AAB dipasang,
        // bukan diunduh belakangan dari internet.
        deliveryType = "install-time"
    }
}
