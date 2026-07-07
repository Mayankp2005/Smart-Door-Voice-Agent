package com.example.smartdoor

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.SharedPreferences
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.cardview.widget.CardView
import androidx.core.app.NotificationCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.smartdoor.databinding.ActivityMainBinding
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query

class MainActivity : AppCompatActivity() {

    private lateinit var db: FirebaseFirestore
    private lateinit var adapter: VisitorAdapter
    private val visitorList = mutableListOf<Visitor>()
    
    // UI Elements
    private lateinit var switchAgent: SwitchMaterial
    private lateinit var webViewCamera: WebView
    private lateinit var cardApproval: CardView
    private lateinit var textVisitorInfo: TextView
    private lateinit var btnApprove: Button
    private lateinit var btnDeny: Button
    private lateinit var emptyView: TextView
    private lateinit var textCameraStatus: TextView

    private var currentPendingDocId: String? = null
    private lateinit var sharedPreferences: SharedPreferences
    
    companion object {
        const val CHANNEL_ID = "visitor_alert_channel"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        db = FirebaseFirestore.getInstance()
        sharedPreferences = getSharedPreferences("SmartDoorPrefs", MODE_PRIVATE)

        // Initialize UI Refs
        switchAgent = findViewById(R.id.switchAgent)
        webViewCamera = findViewById(R.id.webViewCamera)
        cardApproval = findViewById(R.id.cardApproval)
        textVisitorInfo = findViewById(R.id.textVisitorInfo)
        btnApprove = findViewById(R.id.btnApprove)
        btnDeny = findViewById(R.id.btnDeny)
        emptyView = findViewById(R.id.emptyView)
        textCameraStatus = findViewById(R.id.textCameraStatus)
        
        createNotificationChannel()
        checkNotificationPermission() // Request Permission
        
        setupRecyclerView()
        setupAgentSwitch()
        setupApprovalLogic()
        setupCamera()
        listenForVisitors()
    }

    private fun checkNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != 
                android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 101)
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val name = "Visitor Alerts"
            val descriptionText = "Notifications when a visitor arrives"
            val importance = NotificationManager.IMPORTANCE_HIGH
            val channel = NotificationChannel(CHANNEL_ID, name, importance).apply {
                description = descriptionText
                val audioAttributes = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .build()
                setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), audioAttributes)
                enableVibration(true)
            }
            val notificationManager: NotificationManager =
                getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun sendNotification(visitorName: String) {
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher) 
            .setContentTitle("🚨 Visitor Alert")
            .setContentText("$visitorName is at the door.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION))

        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(1001, builder.build())
    }

    private fun setupCamera() {
        val savedIp = sharedPreferences.getString("pc_ip", "")
        
        webViewCamera.settings.javaScriptEnabled = true
        webViewCamera.settings.loadWithOverviewMode = true
        webViewCamera.settings.useWideViewPort = true
        webViewCamera.webViewClient = WebViewClient()

        if (savedIp.isNullOrEmpty()) {
            textCameraStatus.text = "Tap to Connect Camera"
        } else {
            loadCameraStream(savedIp)
        }
        
        // Allow clicking camera status text to change IP
        findViewById<View>(R.id.textCameraStatus).setOnClickListener {
            showIpDialog()
        }
    }

    private fun showIpDialog() {
        val builder = AlertDialog.Builder(this)
        builder.setTitle("Enter PC IP Address")
        builder.setMessage("Enter ONLY the IP (e.g., 192.168.1.5)")

        val input = EditText(this)
        val savedIp = sharedPreferences.getString("pc_ip", "")
        input.setText(savedIp)
        builder.setView(input)

        builder.setPositiveButton("Connect") { _, _ ->
            var ip = input.text.toString().trim()
            // Basic cleanup if user accidentally pastes full URL
            ip = ip.replace("http://", "").replace("/", "").replace(":5000", "")
            
            if (ip.isNotEmpty()) {
                sharedPreferences.edit().putString("pc_ip", ip).apply()
                loadCameraStream(ip)
            }
        }
        builder.setNegativeButton("Cancel") { dialog, _ -> dialog.cancel() }
        builder.show()
    }

    private fun loadCameraStream(ip: String) {
        val url = "http://$ip:5000/video_feed"
        textCameraStatus.text = "" 
        textCameraStatus.visibility = View.GONE // Hide text on video
        webViewCamera.loadUrl(url)
    }

    private fun setupAgentSwitch() {
        val docRef = db.collection("config").document("settings")
        
        // Listen to remote state
        docRef.addSnapshotListener { snapshot, e ->
            if (e != null) return@addSnapshotListener
            if (snapshot != null && snapshot.exists()) {
                val isActive = snapshot.getBoolean("agent_active") ?: true
                switchAgent.isChecked = isActive
                switchAgent.text = if (isActive) "Active" else "Paused"
            }
        }

        // Update remote state on click
        switchAgent.setOnCheckedChangeListener { _, isChecked ->
            switchAgent.text = if (isChecked) "Active" else "Paused"
            docRef.set(mapOf("agent_active" to isChecked))
        }
    }

    private fun setupApprovalLogic() {
        btnApprove.setOnClickListener {
            currentPendingDocId?.let { id ->
                db.collection("visitors").document(id).update("status", "APPROVED")
                Toast.makeText(this, "Visitor Approved", Toast.LENGTH_SHORT).show()
                cardApproval.visibility = View.GONE
            }
        }

        btnDeny.setOnClickListener {
             currentPendingDocId?.let { id ->
                db.collection("visitors").document(id).update("status", "DENIED")
                Toast.makeText(this, "Visitor Denied", Toast.LENGTH_SHORT).show()
                cardApproval.visibility = View.GONE
            }
        }
    }

    private fun deleteVisitor(visitor: Visitor) {
        if (visitor.id.isNotEmpty()) {
            db.collection("visitors").document(visitor.id)
                .delete()
                .addOnSuccessListener { 
                    Toast.makeText(this, "Visitor Deleted", Toast.LENGTH_SHORT).show()
                }
                .addOnFailureListener { e ->
                    Toast.makeText(this, "Error deleting: ${e.message}", Toast.LENGTH_SHORT).show()
                }
        }
    }

    private fun setupRecyclerView() {
        adapter = VisitorAdapter(visitorList) { visitor ->
            deleteVisitor(visitor)
        }
        val recyclerView = findViewById<RecyclerView>(R.id.recyclerView)
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter
    }

    private fun listenForVisitors() {
        db.collection("visitors")
            .orderBy("timestamp", Query.Direction.DESCENDING)
            .addSnapshotListener { snapshots, e ->
                if (e != null) {
                    Log.w("Firestore", "Listen failed.", e)
                    return@addSnapshotListener
                }

                if (snapshots != null) {
                    visitorList.clear()
                    var latestVisitor: Visitor? = null
                    var latestDocId: String? = null
                    
                    for (doc in snapshots) {
                        val v = doc.toObject(Visitor::class.java)
                        v.id = doc.id
                        visitorList.add(v)
                        
                        if (latestVisitor == null) {
                            latestVisitor = v
                            latestDocId = doc.id
                        }
                    }
                    
                    adapter.notifyDataSetChanged()
                    
                    if (visitorList.isEmpty()) {
                        emptyView.visibility = View.VISIBLE
                    } else {
                        emptyView.visibility = View.GONE
                    }

                    // Check for Pending Status on the LATEST visitor
                    if (latestVisitor != null && latestVisitor.status == "PENDING") {
                        if (currentPendingDocId != latestDocId) {
                            // New pending visitor detected!
                             sendNotification(latestVisitor.name)
                        }
                        currentPendingDocId = latestDocId
                        showApprovalCard(latestVisitor)
                    } else {
                        cardApproval.visibility = View.GONE
                        currentPendingDocId = null
                    }
                }
            }
    }
    
    private fun showApprovalCard(visitor: Visitor) {
        cardApproval.visibility = View.VISIBLE
        textVisitorInfo.text = "Name: ${visitor.name}\nPurpose: ${visitor.purpose}"
    }
}
