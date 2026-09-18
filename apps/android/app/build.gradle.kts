plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val mobileBaseUrl = providers.gradleProperty("KISSNE_MOBILE_BASE_URL")
    .orElse("https://yeqingxu.cyou/mobile/")

android {
    namespace = "com.kissne.mobile"
    compileSdk = 35
    buildFeatures {
        buildConfig = true
    }
    defaultConfig {
        applicationId = "com.kissne.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Source: Soul §0.3.16 production HTTPS mobile adapter entrypoint.
        buildConfigField("String", "MOBILE_BASE_URL", "\"${mobileBaseUrl.get()}\"")
    }
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
    testImplementation("junit:junit:4.13.2")
}
