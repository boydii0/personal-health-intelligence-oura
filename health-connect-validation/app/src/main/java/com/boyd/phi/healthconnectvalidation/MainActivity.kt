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
import androidx.health.connect.client.records.BodyFatRecord
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

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var healthConnectClient: HealthConnectClient
    private lateinit var statusView: TextView
    private var pendingExport: String? = null

    private val permissions = setOf(
        HealthPermission.getReadPermission(WeightRecord::class),
        HealthPermission.getReadPermission(BodyFatRecord::class)
    )

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        statusView.text = if (granted.containsAll(permissions)) {
            "Permissions granted: Weight + Body Fat read-only."
        } else {
            "Required permissions were not fully granted. No data was read."
        }
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
        statusView.text = "Validation export written to the location you selected."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        statusView = TextView(this).apply {
            textSize = 16f
            text = "Checking Health Connect availability…"
        }
        val grantButton = Button(this).apply {
            text = "Grant Weight + Body Fat read access"
            isEnabled = false
        }
        val readButton = Button(this).apply {
            text = "Read last 30 days and export JSON"
            isEnabled = false
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
            addView(statusView, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ))
            addView(grantButton)
            addView(readButton)
        }
        setContentView(root)

        when (HealthConnectClient.getSdkStatus(this)) {
            HealthConnectClient.SDK_AVAILABLE -> {
                healthConnectClient = HealthConnectClient.getOrCreate(this)
                statusView.text = "Health Connect available. No health data has been read yet."
                grantButton.isEnabled = true
                readButton.isEnabled = true
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                statusView.text = "Health Connect requires an update before validation can run."
            }
            else -> {
                statusView.text = "Health Connect is unavailable on this device."
            }
        }

        grantButton.setOnClickListener {
            scope.launch {
                val granted = healthConnectClient.permissionController.getGrantedPermissions()
                if (granted.containsAll(permissions)) {
                    statusView.text = "Weight + Body Fat read permissions are already granted."
                } else {
                    permissionLauncher.launch(permissions)
                }
            }
        }

        readButton.setOnClickListener {
            scope.launch {
                val granted = healthConnectClient.permissionController.getGrantedPermissions()
                if (!granted.containsAll(permissions)) {
                    statusView.text = "Grant Weight + Body Fat read permissions before reading."
                    return@launch
                }
                statusView.text = "Reading bounded 30-day window…"
                runCatching { buildValidationExport() }
                    .onSuccess { json ->
                        pendingExport = json
                        val stamp = Instant.now().toString().replace(':', '-')
                        exportLauncher.launch("phi-hume-health-connect-$stamp.json")
                    }
                    .onFailure { error ->
                        statusView.text = "Read failed closed: ${error.javaClass.simpleName}: ${error.message ?: "unknown error"}"
                    }
            }
        }
    }

    private suspend fun buildValidationExport(): String = withContext(Dispatchers.IO) {
        val end = Instant.now()
        val start = end.minus(30, ChronoUnit.DAYS)

        val weightRecords = healthConnectClient.readRecords(
            ReadRecordsRequest(
                recordType = WeightRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end),
                ascendingOrder = true
            )
        ).records

        val bodyFatRecords = healthConnectClient.readRecords(
            ReadRecordsRequest(
                recordType = BodyFatRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end),
                ascendingOrder = true
            )
        ).records

        val records = JSONArray()
        weightRecords.forEach { record ->
            records.put(
                commonMetadata(record.metadata)
                    .put("record_type", "weight")
                    .put("observed_at_utc", record.time.toString())
                    .put("zone_offset", record.zoneOffset?.toString())
                    .put("value", record.weight.inKilograms)
                    .put("unit", "kg")
            )
        }
        bodyFatRecords.forEach { record ->
            records.put(
                commonMetadata(record.metadata)
                    .put("record_type", "body_fat")
                    .put("observed_at_utc", record.time.toString())
                    .put("zone_offset", record.zoneOffset?.toString())
                    .put("value", record.percentage.value)
                    .put("unit", "percent")
            )
        }

        JSONObject()
            .put("schema_version", "phi.health_connect_validation.v0.1")
            .put("generated_at_utc", Instant.now().toString())
            .put("query_start_utc", start.toString())
            .put("query_end_utc", end.toString())
            .put("query_window_days", 30)
            .put("read_only", true)
            .put("network_transmission", false)
            .put("record_count", records.length())
            .put("records", records)
            .toString(2)
    }

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
