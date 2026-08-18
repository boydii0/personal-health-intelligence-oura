plugins {
    id("com.android.application")
}

android {
    namespace = "com.boyd.phi.healthconnectvalidation"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.boyd.phi.healthconnectvalidation"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.13.0")
    implementation("androidx.health.connect:connect-client:1.1.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
}
