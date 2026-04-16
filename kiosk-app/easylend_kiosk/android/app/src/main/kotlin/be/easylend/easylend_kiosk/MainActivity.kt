package be.easylend.easylend_kiosk

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.os.Build
import android.util.Log
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {

	override fun onStart() {
		super.onStart()
		configureKioskPolicies()
	}

	private fun configureKioskPolicies() {
		val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
		val admin = ComponentName(this, KioskDeviceAdminReceiver::class.java)

		if (!dpm.isDeviceOwnerApp(packageName)) {
			return
		}

		if (!dpm.isAdminActive(admin)) {
			Log.w("EasyLendKiosk", "Device owner is set but admin receiver is not active for current UID.")
			return
		}

		try {
			dpm.setLockTaskPackages(admin, arrayOf(packageName))
			if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
				dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
			} else {
				Log.i("EasyLendKiosk", "Skipping lock task feature configuration on API < 28.")
			}
		} catch (se: SecurityException) {
			Log.e("EasyLendKiosk", "Unable to configure lock task policies", se)
		}
	}
}
