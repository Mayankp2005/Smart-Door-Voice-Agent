package com.example.smartdoor

import com.google.firebase.Timestamp

data class Visitor(
    val name: String = "",
    val purpose: String = "",
    val timestamp: Timestamp? = null,
    val date_str: String = "",
    val status: String = "",
    var id: String = ""
)
