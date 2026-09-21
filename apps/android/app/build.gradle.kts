plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val mobileBaseUrl = providers.gradleProperty("KISSNE_MOBILE_BASE_URL")
    .orElse("https://yeqingxu.cyou/mobile/")

val releaseStorePath = providers.environmentVariable("KISSNE_ANDROID_KEYSTORE_PATH").orNull
val releaseStorePassword = providers.environmentVariable("KISSNE_ANDROID_STORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("KISSNE_ANDROID_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("KISSNE_ANDROID_KEY_PASSWORD").orNull
val hasReleaseSigning = listOf(
    releaseStorePath, releaseStorePassword, releaseKeyAlias, releaseKeyPassword
).all { !it.isNullOrBlank() }

android {
    namespace = "com.kissne.mobile"
    compileSdk = 35
    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("kissneDebugStable") {
            // Intentionally checked in for the .debug application only.
            // This is not the production/release signing identity.
            storeFile = file("signing/kissne-debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
        if (hasReleaseSigning) {
            create("kissneRelease") {
                storeFile = file(releaseStorePath!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    defaultConfig {
        applicationId = "com.kissne.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 12
        versionName = "0.2.10"
        manifestPlaceholders["appLabel"] = "Kissne"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "MOBILE_BASE_URL", "\"${mobileBaseUrl.get()}\"")
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-dev"
            manifestPlaceholders["appLabel"] = "Kissne Dev"
            signingConfig = signingConfigs.getByName("kissneDebugStable")
        }
        getByName("release") {
            isMinifyEnabled = false
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("kissneRelease")
            }
        }
    }

    sourceSets["main"].assets.srcDir(file("../../../kissne-prototype/prototype"))
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("androidx.webkit:webkit:1.12.1")
    testImplementation("junit:junit:4.13.2")
}
