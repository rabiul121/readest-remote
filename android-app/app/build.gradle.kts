plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.readestremote"
    compileSdk = 35

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.example.readestremote"
        minSdk = 26
        targetSdk = 35
        versionCode = 17
        versionName = "1.7.1"
    }

    buildTypes {
        getByName("release") {
            // Produces a locally installable APK; replace with a private release key before store distribution.
            signingConfig = signingConfigs.getByName("debug")
            isMinifyEnabled = false
        }
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}
