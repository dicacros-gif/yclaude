package com.yclaude.app

import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButtonToggleGroup

class MainActivity : AppCompatActivity() {

    private lateinit var modeGroup: MaterialButtonToggleGroup
    private lateinit var keywordsInput: EditText
    private lateinit var songInput: EditText
    private lateinit var lyricsInput: EditText
    private lateinit var hoursInput: EditText
    private lateinit var minutesInput: EditText
    private lateinit var tsRow: View
    private lateinit var titleOut: EditText
    private lateinit var descOut: EditText
    private lateinit var tagsOut: EditText
    private lateinit var status: TextView

    private var isShorts = true
    private var hasOutput = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        modeGroup = findViewById(R.id.modeGroup)
        keywordsInput = findViewById(R.id.keywordsInput)
        songInput = findViewById(R.id.songInput)
        lyricsInput = findViewById(R.id.lyricsInput)
        hoursInput = findViewById(R.id.hoursInput)
        minutesInput = findViewById(R.id.minutesInput)
        tsRow = findViewById(R.id.tsRow)
        titleOut = findViewById(R.id.titleOut)
        descOut = findViewById(R.id.descOut)
        tagsOut = findViewById(R.id.tagsOut)
        status = findViewById(R.id.status)

        modeGroup.check(R.id.btnShorts)
        applyMode()
        modeGroup.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            isShorts = checkedId == R.id.btnShorts
            applyMode()
            if (hasOutput) generate() // re-roll in the newly selected mode
        }

        findViewById<Button>(R.id.btnGenerate).setOnClickListener { generate() }
        findViewById<Button>(R.id.btnRegen).setOnClickListener { generate() }
        findViewById<Button>(R.id.btnCopyTitle).setOnClickListener { copy("제목", titleOut) }
        findViewById<Button>(R.id.btnCopyDesc).setOnClickListener { copy("설명", descOut) }
        findViewById<Button>(R.id.btnCopyTags).setOnClickListener { copy("태그", tagsOut) }

        enableInnerScroll(lyricsInput)
        enableInnerScroll(descOut)
    }

    private fun applyMode() {
        tsRow.visibility = if (isShorts) View.GONE else View.VISIBLE
        status.text = if (isShorts) "Shorts 모드 · 제목 설명 태그 생성"
        else "롱폼 모드 · 영상 길이를 넣으면 타임스탬프가 맞춰집니다"
    }

    private fun generate() {
        val kw = keywordsInput.text.toString().trim()
        val song = songInput.text.toString().trim()
        val lyr = lyricsInput.text.toString()
        if (kw.isBlank() && song.isBlank() && lyr.isBlank()) {
            toast("키워드나 노래 제목을 입력하세요")
            return
        }
        val input = MetaInput(
            keywords = kw,
            songTitle = song,
            lyrics = lyr,
            hours = hoursInput.text.toString().trim().toIntOrNull() ?: 0,
            minutes = minutesInput.text.toString().trim().toIntOrNull() ?: 0,
            isShorts = isShorts
        )
        val r = MetaGen.generate(input)
        titleOut.setText(r.title)
        descOut.setText(r.description)
        tagsOut.setText(r.tags)
        hasOutput = true
        status.text = if (isShorts) "Shorts 생성 완료 · 마음에 안 들면 재생성"
        else "롱폼 생성 완료 · 마음에 안 들면 재생성"
    }

    private fun copy(label: String, field: EditText) {
        val t = field.text?.toString()?.takeIf { it.isNotBlank() }
        if (t == null) {
            toast("먼저 생성하세요")
            return
        }
        val cb = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cb.setPrimaryClip(ClipData.newPlainText(label, t))
        toast("$label 복사됨")
    }

    /** Keep multi line boxes scrollable inside the outer ScrollView. */
    @SuppressLint("ClickableViewAccessibility")
    private fun enableInnerScroll(v: View) {
        v.setOnTouchListener { view, ev ->
            view.parent?.requestDisallowInterceptTouchEvent(true)
            if (ev.actionMasked == MotionEvent.ACTION_UP ||
                ev.actionMasked == MotionEvent.ACTION_CANCEL
            ) {
                view.parent?.requestDisallowInterceptTouchEvent(false)
            }
            false
        }
    }

    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()
}
