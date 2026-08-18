# PHI Step 5A — Hume / Android Health Connect Validation

Status: **DRAFT / LOCAL DEVICE VALIDATION REQUIRED**

This folder contains a deliberately bounded Android validation utility for PHI Step 5A. It is **not** the deferred Personal Health App and is not a production sync service.

## Purpose

Prove whether Hume-origin `WeightRecord` and `BodyFatRecord` entries exist in Android Health Connect and preserve enough provenance to support deterministic PHI normalization.

## Security / authority ceiling

The app requests only:

- `android.permission.health.READ_WEIGHT`
- `android.permission.health.READ_BODY_FAT`

It does **not** request Health Connect write permissions, background health-data access, expanded historical access, Internet access, or cloud credentials. Reads are bounded to 30 days and export is user-initiated through the Android system file picker.

**Never commit exported JSON or other health data to this repository.** The public GitHub repository is code/documentation only.

## Local validation sequence

1. Open `health-connect-validation/` in Android Studio.
2. Sync Gradle.
3. Build/install on the Android phone that contains the Hume → Health Connect data.
4. Grant **Weight** and **Body Fat** read access only.
5. Read the bounded 30-day window and save the JSON outside the Git repository.
6. Inspect `data_origin_package` values; do not assume Hume's package name.
7. Compare 3–5 candidate Hume records with the Hume app.
8. Only after PASS should Step 5B normalization proceed.

## Build assumptions

- JDK 17
- Android Gradle Plugin 9.2.0 / Gradle 9.4.1+
- compile/target SDK 36
- Health Connect Jetpack 1.1.0 stable
- AndroidX Activity 1.13.0

No Gradle wrapper is committed in this draft; use Android Studio / local Gradle for initial build validation.

## Sources

- https://developer.android.com/health-and-fitness/health-connect
- https://developer.android.com/health-and-fitness/health-connect/get-started
- https://developer.android.com/health-and-fitness/health-connect/read-data
- https://developer.android.com/reference/androidx/health/connect/client/records/WeightRecord
- https://developer.android.com/reference/androidx/health/connect/client/records/BodyFatRecord
- https://developer.android.com/reference/kotlin/androidx/health/connect/client/records/metadata/DataOrigin
