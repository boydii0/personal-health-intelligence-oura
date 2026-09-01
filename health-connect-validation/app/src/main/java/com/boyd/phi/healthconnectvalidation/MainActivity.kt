package com.boyd.phi.healthconnectvalidation

import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.BasalMetabolicRateRecord
import androidx.health.connect.client.records.BodyFatRecord
import androidx.health.connect.client.records.BodyWaterMassRecord
import androidx.health.connect.client.records.BoneMassRecord
import androidx.health.connect.client.records.LeanBodyMassRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.temporal.ChronoUnit

class MainActivity : ComponentActivity() {

    companion object {
        private const val HUME_PACKAGE = "com.elink.fittrackhealth.pro"
        private const val WINDOW_DAYS = 30L
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var healthConnectClient: HealthConnectClient
    private lateinit var statusView: TextView
    private var pendingExport: String? = null

    private val validatedPermissions = setOf(
        HealthPermission.getReadPermission(WeightRecord::class),
        HealthPermission.getReadPermission(BodyFatRecord::class)
    )

    private val candidatePermissions = setOf(
        HealthPermission.getReadPermission(LeanBodyMassRecord::class),
        HealthPermission.getReadPermission(BodyWaterMassRecord::class),
        HealthPermission.getReadPermission(BoneMassRecord::class),
        HealthPermission.getReadPermission(BasalMetabolicRateRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class)
    )

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        statusView.text = "Permission request completed. Granted ${granted.size} requested read permission(s)."
    }

    private val exportLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri: Uri? ->
        if (uri == null) {
            statusView.text = "Export cancelled. No file was written."
            return@registerForActivityResult
        }
        val payload = pendingExport ?: return@registerForActivityResult
        contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { it.write(payload) }
        statusView.text = "Read-only Health Connect export written to the location you selected."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        statusView = TextView(this).apply {
            textSize = 16f
            text = "Checking Health Connect availability…"
        }
        val grantValidatedButton = Button(this).apply {
            text = "Grant Weight + Body Fat read access"
            isEnabled = false
        }
        val exportValidatedButton = Button(this).apply {
            text = "Export validated Weight + Body Fat (30 days)"
            isEnabled = false
        }
        val grantCandidateButton = Button(this).apply {
            text = "Grant Hume candidate metric read access"
            isEnabled = false
        }
        val probeCandidateButton = Button(this).apply {
            text = "Probe Hume candidate metrics (30 days)"
            isEnabled = false
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
            addView(statusView, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ))
            addView(grantValidatedButton)
            addView(exportValidatedButton)
            addView(grantCandidateButton)
            addView(probeCandidateButton)
        }
        setContentView(root)

        when (HealthConnectClient.getSdkStatus(this)) {
            HealthConnectClient.SDK_AVAILABLE -> {
                healthConnectClient = HealthConnectClient.getOrCreate(this)
                statusView.text = "Health Connect available. No health data has been read yet."
                grantValidatedButton.isEnabled = true
                exportValidatedButton.isEnabled = true
                grantCandidateButton.isEnabled = true
                probeCandidateButton.isEnabled = true
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                statusView.text = "Health Connect requires an update before validation can run."
            }
            else -> {
                statusView.text = "Health Connect is unavailable on this device."
            }
        }

        grantValidatedButton.setOnClickListener {
            requestIfNeeded(validatedPermissions, "Validated Weight + Body Fat permissions are already granted.")
        }

        grantCandidateButton.setOnClickListener {
            requestIfNeeded(candidatePermissions, "All candidate metric read permissions are already granted.")
        }

        exportValidatedButton.setOnClickListener {
            scope.launch {
                if (!hasPermissions(validatedPermissions)) {
                    statusView.text = "Grant Weight + Body Fat read permissions before reading."
                    return@launch
                }
                statusView.text = "Reading validated bounded 30-day window…"
                runCatching { buildValidatedExport() }
                    .onSuccess { export(it, "phi-hume-health-connect") }
                    .onFailure { failClosed(it) }
            }
        }

        probeCandidateButton.setOnClickListener {
            scope.launch {
                if (!hasPermissions(candidatePermissions)) {
                    statusView.text = "Grant candidate read permissions before probing."
                    return@launch
                }
                statusView.text = "Probing Hume candidate metrics over bounded 30-day window…"
                runCatching { buildCandidateProbe() }
                    .onSuccess { export(it, "phi-hume-health-connect-capability-probe") }
                    .onFailure { failClosed(it) }
            }
        }
    }

    private fun requestIfNeeded(required: Set<String>, alreadyGrantedMessage: String) {
        scope.launch {
            val granted = healthConnectClient.permissionController.getGrantedPermissions()
            if (granted.containsAll(required)) {
                statusView.text = alreadyGrantedMessage
            } else {
                permissionLauncher.launch(required)
            }
        }
    }

    private suspend fun hasPermissions(required: Set<String>): Boolean =
        healthConnectClient.permissionController.getGrantedPermissions().containsAll(required)

    private fun export(json: String, prefix: String) {
        pendingExport = json
        val stamp = Instant.now().toString().replace(':', '-')
        exportLauncher.launch("$prefix-$stamp.json")
    }

    private fun failClosed(error: Throwable) {
        statusView.text = "Read failed closed: ${error.javaClass.simpleName}: ${error.message ?: "unknown error"}"
    }

    private suspend fun buildValidatedExport(): String = withContext(Dispatchers.IO) {
        val end = Instant.now()
        val start = end.minus(WINDOW_DAYS, ChronoUnit.DAYS)
        val records = JSONArray()

        healthConnectClient.readRecords(
            ReadRecordsRequest(WeightRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(
                commonMetadata(record.metadata)
                    .put("record_type", "weight")
                    .put("observed_at_utc", record.time.toString())
                    .put("zone_offset", record.zoneOffset?.toString())
                    .put("value", record.weight.inKilograms)
                    .put("unit", "kg")
            )
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(BodyFatRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(
                commonMetadata(record.metadata)
                    .put("record_type", "body_fat")
                    .put("observed_at_utc", record.time.toString())
                    .put("zone_offset", record.zoneOffset?.toString())
                    .put("value", record.percentage.value)
                    .put("unit", "percent")
            )
        }

        envelope("phi.health_connect_validation.v0.2", start, end, records)
            .put("mode", "validated_weight_body_fat")
            .toString(2)
    }

    private suspend fun buildCandidateProbe(): String = withContext(Dispatchers.IO) {
        val end = Instant.now()
        val start = end.minus(WINDOW_DAYS, ChronoUnit.DAYS)
        val records = JSONArray()

        healthConnectClient.readRecords(
            ReadRecordsRequest(LeanBodyMassRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "lean_body_mass").put("observed_at_utc", record.time.toString()).put("zone_offset", record.zoneOffset?.toString()).put("value", record.mass.inKilograms).put("unit", "kg"))
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(BodyWaterMassRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "body_water_mass").put("observed_at_utc", record.time.toString()).put("zone_offset", record.zoneOffset?.toString()).put("value", record.mass.inKilograms).put("unit", "kg"))
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(BoneMassRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "bone_mass").put("observed_at_utc", record.time.toString()).put("zone_offset", record.zoneOffset?.toString()).put("value", record.mass.inKilograms).put("unit", "kg"))
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(BasalMetabolicRateRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "basal_metabolic_rate").put("observed_at_utc", record.time.toString()).put("zone_offset", record.zoneOffset?.toString()).put("value", record.basalMetabolicRate.inWatts).put("unit", "W"))
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(ActiveCaloriesBurnedRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "active_calories_burned").put("start_time_utc", record.startTime.toString()).put("end_time_utc", record.endTime.toString()).put("start_zone_offset", record.startZoneOffset?.toString()).put("end_zone_offset", record.endZoneOffset?.toString()).put("value", record.energy.inKilocalories).put("unit", "kcal"))
        }

        healthConnectClient.readRecords(
            ReadRecordsRequest(TotalCaloriesBurnedRecord::class, TimeRangeFilter.between(start, end), ascendingOrder = true)
        ).records.forEach { record ->
            records.put(commonMetadata(record.metadata).put("record_type", "total_calories_burned").put("start_time_utc", record.startTime.toString()).put("end_time_utc", record.endTime.toString()).put("start_zone_offset", record.startZoneOffset?.toString()).put("end_zone_offset", record.endZoneOffset?.toString()).put("value", record.energy.inKilocalories).put("unit", "kcal"))
        }

        val allOrigins = mutableSetOf<String>()
        val humeTypes = mutableSetOf<String>()
        for (i in 0 until records.length()) {
            val r = records.getJSONObject(i)
            val origin = r.optString("data_origin_package")
            val type = r.optString("record_type")
            if (origin.isNotBlank()) allOrigins.add(origin)
            if (origin == HUME_PACKAGE && type.isNotBlank()) humeTypes.add(type)
        }

        envelope("phi.health_connect_capability_probe.v0.1", start, end, records)
            .put("mode", "candidate_metric_inventory")
            .put("expected_hume_package", HUME_PACKAGE)
            .put("observed_data_origins", JSONArray(allOrigins.sorted()))
            .put("hume_origin_record_types", JSONArray(humeTypes.sorted()))
            .put("hume_origin_record_count", (0 until records.length()).count { records.getJSONObject(it).optString("data_origin_package") == HUME_PACKAGE })
            .put("authorization_effect", "probe_only_no_production_scope_change")
            .toString(2)
    }

    private fun envelope(schema: String, start: Instant, end: Instant, records: JSONArray): JSONObject =
        JSONObject()
            .put("schema_version", schema)
            .put("generated_at_utc", Instant.now().toString())
            .put("query_start_utc", start.toString())
            .put("query_end_utc", end.toString())
            .put("query_window_days", WINDOW_DAYS)
            .put("read_only", true)
            .put("network_transmission", false)
            .put("record_count", records.length())
            .put("records", records)

    private fun commonMetadata(metadata: androidx.health.connect.client.records.metadata.Metadata): JSONObject {
        val device = metadata.device
        return JSONObject()
            .put("record_id", metadata.id)
            .put("data_origin_package", metadata.dataOrigin.packageName)
            .put("last_modified_at_utc", metadata.lastModifiedTime.toString())
            .put("recording_method", metadata.recordingMethod)
            .put("device_manufacturer", device?.manufacturer)
            .put("device_model", device?.model)
            .put("device_type", device?.type)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
