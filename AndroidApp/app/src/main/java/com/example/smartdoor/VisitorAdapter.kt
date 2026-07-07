package com.example.smartdoor

import android.content.Context
import android.graphics.Color
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView

class VisitorAdapter(
    private val visitors: List<Visitor>,
    private val onDeleteClick: (Visitor) -> Unit
) : RecyclerView.Adapter<VisitorAdapter.VisitorViewHolder>() {

    class VisitorViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val textName: TextView = itemView.findViewById(R.id.textName)
        val textPurpose: TextView = itemView.findViewById(R.id.textPurpose)
        val textTime: TextView = itemView.findViewById(R.id.textTime)
        val textStatus: TextView = itemView.findViewById(R.id.textStatus)
    val cardStatus: MaterialCardView = itemView.findViewById(R.id.cardStatus)
        val btnDelete: android.widget.ImageButton = itemView.findViewById(R.id.btnDelete)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VisitorViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_visitor, parent, false)
        return VisitorViewHolder(view)
    }

    override fun onBindViewHolder(holder: VisitorViewHolder, position: Int) {
        val visitor = visitors[position]
        val context = holder.itemView.context

        holder.textName.text = visitor.name
        holder.textPurpose.text = "Purpose: ${visitor.purpose}"
        holder.textTime.text = visitor.date_str
        
        // Status Logic
        val status = visitor.status.uppercase()
        holder.textStatus.text = status

        val colorRes = when (status) {
            "APPROVED" -> R.color.statusApproved
            "DENIED" -> R.color.statusDenied
            "PENDING" -> R.color.statusPending
            else -> android.R.color.darker_gray
        }

        holder.cardStatus.setCardBackgroundColor(ContextCompat.getColor(context, colorRes))
        
        holder.btnDelete.setOnClickListener {
            onDeleteClick(visitor)
        }
    }

    override fun getItemCount() = visitors.size
}
