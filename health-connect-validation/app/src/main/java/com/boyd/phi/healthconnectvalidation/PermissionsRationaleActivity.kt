package com.boyd.phi.healthconnectvalidation

import android.app.Activity
import android.os.Bundle
import android.widget.ScrollView
import android.widget.TextView

class PermissionsRationaleActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val text = TextView(this).apply {
            textSize = 17f
            setPadding(48, 48, 48, 48)
            text = """
                PHI Health Connect Validator — Privacy Rationale

                Purpose: validate whether Hume-origin Weight and Body Fat records are present in Android Health Connect for the Personal Health Intelligence project.

                This validation app:
                • reads Weight and Body Fat only;
                • uses a bounded 30-day foreground query;
                • does not write or delete Health Connect data;
                • does not request background or expanded-history access;
                • does not request Internet access or transmit health data;
                • exports JSON only after you explicitly choose a destination with the Android system file picker.

                Exported health data must remain outside the public GitHub repository and be handled under the PHI project governance controls.
            """.trimIndent()
        }

        setContentView(ScrollView(this).apply { addView(text) })
    }
}
