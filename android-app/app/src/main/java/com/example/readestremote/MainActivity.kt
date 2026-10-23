package com.example.readestremote

import android.app.Activity
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.text.method.SingleLineTransformationMethod
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.util.Base64
import java.util.concurrent.Executors
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("remote_settings", MODE_PRIVATE) }

    private lateinit var hostInput: EditText
    private lateinit var portInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var status: TextView
    private lateinit var statusDot: View
    private lateinit var saveButton: Button
    private var tokenVisible = false
    private var busy = false
    private var themeMode = THEME_AUTO
    private var readingMode = MODE_NORMAL
    private var receiverMode = MODE_NORMAL
    private var modeRequestPending = false
    private var showSettings = false

    private data class Palette(
        val background: Int,
        val surface: Int,
        val raised: Int,
        val foreground: Int,
        val muted: Int,
        val outline: Int,
        val accent: Int,
        val accentText: Int,
        val success: Int,
        val danger: Int,
    )

    private val palette: Palette
        get() {
            val systemDark = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
                Configuration.UI_MODE_NIGHT_YES
            val dark = themeMode == THEME_DARK || (themeMode == THEME_AUTO && systemDark)
            return if (dark) Palette(
                background = Color.rgb(13, 19, 32),
                surface = Color.rgb(24, 33, 49),
                raised = Color.rgb(37, 49, 68),
                foreground = Color.rgb(239, 244, 252),
                muted = Color.rgb(166, 180, 200),
                outline = Color.rgb(66, 82, 106),
                accent = Color.rgb(83, 143, 255),
                accentText = Color.WHITE,
                success = Color.rgb(89, 204, 150),
                danger = Color.rgb(255, 126, 126),
            ) else Palette(
                background = Color.rgb(243, 247, 252),
                surface = Color.WHITE,
                raised = Color.rgb(230, 238, 249),
                foreground = Color.rgb(24, 37, 57),
                muted = Color.rgb(91, 107, 128),
                outline = Color.rgb(202, 214, 230),
                accent = Color.rgb(38, 100, 206),
                accentText = Color.WHITE,
                success = Color.rgb(22, 137, 88),
                danger = Color.rgb(190, 54, 54),
            )
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        themeMode = prefs.getString(KEY_THEME_MODE, THEME_AUTO) ?: THEME_AUTO
        // Start with Normal selected in the remote UI. Keep the last successful
        // receiver mode separately so the next command can deactivate it.
        readingMode = MODE_NORMAL
        receiverMode = prefs.getString(KEY_READING_MODE, MODE_NORMAL) ?: MODE_NORMAL
        showSettings = !hasSavedPairing()
        renderUi()
    }

    private fun renderUi() {
        val hostDraft = if (::hostInput.isInitialized) hostInput.text.toString() else prefs.getString(KEY_HOST, "") ?: ""
        val portDraft = if (::portInput.isInitialized) portInput.text.toString() else prefs.getString(KEY_PORT, "18765") ?: "18765"
        val tokenDraft = if (::tokenInput.isInitialized) tokenInput.text.toString() else readStoredSecret()
        val colors = palette
        window.statusBarColor = colors.background
        window.navigationBarColor = colors.background
        @Suppress("DEPRECATION")
        run {
            window.decorView.systemUiVisibility = if (isLight(colors.background)) {
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
            } else 0
        }

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(18), dp(20), dp(22))
            setBackgroundColor(colors.background)
        }

        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            if (showSettings) addView(content)
        }
        val insetTarget: View = if (showSettings) scroll else content
        insetTarget.setOnApplyWindowInsetsListener { _, insets ->
                val topInset: Int
                val bottomInset: Int
                if (Build.VERSION.SDK_INT >= 30) {
                    val bars = insets.getInsets(WindowInsets.Type.systemBars())
                    topInset = bars.top
                    bottomInset = bars.bottom
                } else {
                    @Suppress("DEPRECATION")
                    run {
                        topInset = insets.systemWindowInsetTop
                        bottomInset = insets.systemWindowInsetBottom
                    }
                }
                content.setPadding(dp(20), dp(18) + topInset, dp(20), dp(22) + bottomInset)
                insets
        }

        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val titleBlock = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        titleBlock.addView(TextView(this).apply {
            text = if (showSettings) "Connection settings" else "Readest Remote"
            textSize = 25f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
            setTextColor(colors.foreground)
        }, matchWrap())
        titleBlock.addView(TextView(this).apply {
            text = if (showSettings) "Pair your phone with the Windows receiver" else "A simple remote for your reading session"
            textSize = 13f
            setTextColor(colors.muted)
            setPadding(0, dp(3), 0, 0)
        }, matchWrap())
        topRow.addView(titleBlock, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        topRow.addView(iconButton(themeIcon(), themeDescription(), colors) {
            themeMode = when (themeMode) {
                THEME_AUTO -> THEME_LIGHT
                THEME_LIGHT -> THEME_DARK
                else -> THEME_AUTO
            }
            prefs.edit().putString(KEY_THEME_MODE, themeMode).apply()
            renderUi()
        }, LinearLayout.LayoutParams(dp(46), dp(46)).apply { marginStart = dp(4) })
        if (showSettings && hasSavedPairing()) {
            topRow.addView(iconButton(R.drawable.ic_back, "Back to remote controls", colors) {
                showSettings = false
                renderUi()
            }, LinearLayout.LayoutParams(dp(46), dp(46)).apply { marginStart = dp(4) })
        } else if (!showSettings) {
            topRow.addView(iconButton(R.drawable.ic_settings, "Connection settings", colors) {
                showSettings = true
                renderUi()
            }, LinearLayout.LayoutParams(dp(46), dp(46)).apply { marginStart = dp(4) })
        }
        content.addView(topRow, matchWrap())

        if (!showSettings) {
            content.addView(sectionLabel("READING MODE", colors), topMargin(14))
            val modeRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            modeRow.addView(readingModeButton("Normal", MODE_NORMAL, R.drawable.ic_reading_mode, colors), weightButton())
            modeRow.addView(readingModeButton("Auto", MODE_AUTOSCROLL, R.drawable.ic_mode_autoscroll, colors), weightButton().apply { marginStart = dp(5) })
            modeRow.addView(readingModeButton("Paragraph", MODE_PARAGRAPH, R.drawable.ic_mode_paragraph, colors), weightButton().apply { marginStart = dp(5) })
            modeRow.addView(readingModeButton("Speed", MODE_SPEED, R.drawable.ic_mode_speed, colors), weightButton().apply { marginStart = dp(5) })
            content.addView(modeRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(64)).apply { topMargin = dp(5) })
        }

        if (!showSettings) {
            content.addView(sectionLabel(when (readingMode) {
                MODE_AUTOSCROLL -> "AUTO SCROLL"
                MODE_PARAGRAPH -> "PARAGRAPH READING"
                MODE_SPEED -> "SPEED READING · WPM"
                else -> "TURN PAGES"
            }, colors), topMargin(18))
            if (readingMode == MODE_AUTOSCROLL) {
                val controls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
                controls.addView(actionButton("−", "Slower auto scroll", colors) { sendAction("autoscroll_slower") }, weightButton())
                controls.addView(actionButton("Ⅱ / ▶", "Pause or resume auto scroll", colors) { sendAction("autoscroll_pause") }, weightButton().apply { marginStart = dp(8); marginEnd = dp(8) })
                controls.addView(actionButton("+", "Faster auto scroll", colors) { sendAction("autoscroll_faster") }, weightButton())
                content.addView(controls, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply { topMargin = dp(6) })
            } else if (readingMode == MODE_SPEED) {
                val controls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
                controls.addView(actionButton("− WPM", "Decrease speed reading pace", colors) { sendAction("speed_slower") }, weightButton())
                controls.addView(actionButton("Ⅱ / ▶", "Pause or resume speed reading", colors) { sendAction("speed_pause") }, weightButton().apply { marginStart = dp(8); marginEnd = dp(8) })
                controls.addView(actionButton("+ WPM", "Increase speed reading pace", colors) { sendAction("speed_faster") }, weightButton())
                content.addView(controls, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply { topMargin = dp(6) })
            }
            val pageRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val isSpeed = readingMode == MODE_SPEED
            pageRow.addView(pageButton("Previous page", R.drawable.ic_page_previous, if (isSpeed) "rsvp_previous" else "previous", colors, tall = true),
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply { marginEnd = dp(8) })
            pageRow.addView(pageButton("Next page", R.drawable.ic_page_next, if (isSpeed) "rsvp_next" else "next", colors, tall = true),
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply { marginStart = dp(8) })
            content.addView(pageRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f).apply {
                topMargin = dp(6)
                bottomMargin = dp(8)
            })

            content.addView(sectionLabel("CHAPTERS", colors), topMargin(if (readingMode == MODE_NORMAL || readingMode == MODE_PARAGRAPH) 22 else 10))
            val chapterRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            chapterRow.addView(pageButton("Previous chapter", R.drawable.ic_chapter_previous, if (isSpeed) "rsvp_previous_chapter" else "previous_chapter", colors, tall = false),
                LinearLayout.LayoutParams(0, dp(76), 1f).apply { marginEnd = dp(8) })
            chapterRow.addView(pageButton("Next chapter", R.drawable.ic_chapter_next, if (isSpeed) "rsvp_next_chapter" else "next_chapter", colors, tall = false),
                LinearLayout.LayoutParams(0, dp(76), 1f).apply { marginStart = dp(8) })
            content.addView(chapterRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(76)).apply {
                topMargin = dp(8)
            })

            val laptopTheme = Button(this).apply {
                text = "Cycle Readest theme"
                contentDescription = "Cycle Readest between Auto, Day, and Night theme modes"
                isAllCaps = false
                textSize = 15f
                setTextColor(colors.foreground)
                backgroundTintList = ColorStateList.valueOf(colors.surface)
                setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_theme_cycle, 0, 0, 0)
                compoundDrawablePadding = dp(12)
                setOnClickListener {
                    vibrate(this)
                    sendAction("theme")
                }
            }
            val fontDown = actionButton("A−", "Decrease Readest font size", colors) {
                sendAction("font_smaller")
            }.apply { textSize = 18f }
            val fontUp = actionButton("A+", "Increase Readest font size", colors) {
                sendAction("font_larger")
            }.apply { textSize = 18f }
            val bottomActions = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER
                addView(fontDown, LinearLayout.LayoutParams(dp(54), dp(56)).apply { marginEnd = dp(6) })
                addView(fontUp, LinearLayout.LayoutParams(dp(54), dp(56)).apply { marginEnd = dp(8) })
                addView(laptopTheme, LinearLayout.LayoutParams(0, dp(56), 1f))
            }
            addStatusLine(content, colors, "Keep Readest focused on the laptop.")
            content.addView(bottomActions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply {
                topMargin = dp(10)
            })
            setContentView(content)
            return
        }

        content.addView(sectionLabel("LAPTOP CONNECTION", colors), topMargin(22))
        val setupCard = card(colors)
        val addressRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        hostInput = field("Laptop Wi-Fi IP", colors).apply {
            setText(hostDraft)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        portInput = field("Port", colors).apply {
            setText(portDraft)
            inputType = InputType.TYPE_CLASS_NUMBER
        }
        addressRow.addView(hostInput, LinearLayout.LayoutParams(0, dp(54), 1f).apply { marginEnd = dp(8) })
        addressRow.addView(portInput, LinearLayout.LayoutParams(dp(105), dp(54)))
        setupCard.addView(addressRow, matchWrap())

        val tokenRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        tokenInput = field("Shared secret from receiver.py", colors).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            setText(tokenDraft)
            setSelection(text.length)
        }
        tokenRow.addView(tokenInput, LinearLayout.LayoutParams(0, dp(54), 1f).apply { marginEnd = dp(6) })
        val reveal = TextView(this).apply {
            text = "Show"
            textSize = 13f
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setTextColor(colors.accent)
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(10), dp(6), dp(10))
            setOnClickListener {
                tokenVisible = !tokenVisible
                tokenInput.transformationMethod = if (tokenVisible) SingleLineTransformationMethod.getInstance()
                else PasswordTransformationMethod.getInstance()
                tokenInput.setSelection(tokenInput.text.length)
                text = if (tokenVisible) "Hide" else "Show"
            }
        }
        tokenRow.addView(reveal, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(54)))
        setupCard.addView(tokenRow, topMargin(8))

        val setupActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        saveButton = Button(this).apply {
            text = "Save pairing"
            isAllCaps = false
            textSize = 14f
            setTextColor(colors.accentText)
            backgroundTintList = ColorStateList.valueOf(colors.accent)
            setOnClickListener {
                if (savePairing(showMessage = false)) {
                    showSettings = false
                    renderUi()
                    updateStatus("Pairing saved securely on this phone.", palette.success)
                }
            }
        }
        setupActions.addView(saveButton, LinearLayout.LayoutParams(0, dp(48), 1f).apply { marginEnd = dp(8) })
        val testButton = Button(this).apply {
            text = "Test connection"
            isAllCaps = false
            textSize = 14f
            setTextColor(colors.foreground)
            backgroundTintList = ColorStateList.valueOf(colors.raised)
            setOnClickListener { sendHealthCheck() }
        }
        setupActions.addView(testButton, LinearLayout.LayoutParams(0, dp(48), 1f))
        setupCard.addView(setupActions, topMargin(10))

        addStatusLine(setupCard, colors, "Enter your laptop address, port, and receiver secret.")
        content.addView(setupCard, topMargin(8))

        setContentView(scroll)
    }

    private fun pageButton(
        label: String,
        icon: Int,
        action: String,
        colors: Palette,
        tall: Boolean,
    ): LinearLayout {
        val control = LinearLayout(this).apply {
            orientation = if (tall) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            background = rounded(if (tall) colors.accent else colors.surface, if (tall) Color.TRANSPARENT else colors.outline, 18)
            isClickable = true
            isFocusable = true
            contentDescription = label
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }
        val iconView = ImageView(this).apply {
            setImageResource(icon)
            imageTintList = ColorStateList.valueOf(if (tall) colors.accentText else colors.accent)
            contentDescription = null
        }
        control.addView(iconView, LinearLayout.LayoutParams(dp(if (tall) 42 else 34), dp(if (tall) 42 else 34)).apply {
            if (tall) bottomMargin = dp(6) else marginEnd = dp(8)
        })
        control.addView(TextView(this).apply {
            text = label
            textSize = if (tall) 17f else 13f
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            gravity = Gravity.CENTER
            setTextColor(if (tall) colors.accentText else colors.foreground)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        if (tall) {
            var held = false
            var repeatCount = 0
            val repeat = object : Runnable {
                override fun run() {
                    if (!held) return
                    repeatCount++
                    vibrate(control)
                    sendAction(action, updateStatus = repeatCount == 1)
                    handler.postDelayed(this, 330)
                }
            }
            control.setOnTouchListener { view, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> {
                        held = true
                        repeatCount = 0
                        vibrate(control)
                        handler.postDelayed(repeat, 480)
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        held = false
                        handler.removeCallbacks(repeat)
                        if (repeatCount == 0) {
                            sendAction(action)
                        }
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        held = false
                        handler.removeCallbacks(repeat)
                        true
                    }
                    else -> true
                }
            }
            control.setOnClickListener { /* Touch handling sends the command. */ }
        } else {
            control.setOnClickListener {
                vibrate(control)
                sendAction(action)
            }
        }
        return control
    }

    private fun iconButton(icon: Int, description: String, colors: Palette, onClick: () -> Unit): ImageView =
        ImageView(this).apply {
            setImageResource(icon)
            imageTintList = ColorStateList.valueOf(colors.foreground)
            background = rounded(colors.surface, colors.outline, 14)
            setPadding(dp(11), dp(11), dp(11), dp(11))
            contentDescription = description
            isClickable = true
            isFocusable = true
            setOnClickListener {
                vibrate(this)
                onClick()
            }
        }

    private fun readingModeButton(label: String, mode: String, icon: Int, colors: Palette) =
        LinearLayout(this).apply {
            val selected = readingMode == mode
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            background = rounded(if (selected) colors.accent else colors.surface, if (selected) Color.TRANSPARENT else colors.outline, 14)
            isClickable = true
            isFocusable = true
            isEnabled = !modeRequestPending
            alpha = if (isEnabled) 1f else 0.55f
            contentDescription = "$label reading mode${if (selected) ", selected" else ""}"
            val iconView = ImageView(this@MainActivity).apply {
                setImageResource(icon)
                imageTintList = ColorStateList.valueOf(if (selected) colors.accentText else colors.accent)
            }
            addView(iconView, LinearLayout.LayoutParams(dp(23), dp(23)))
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 11f
                typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
                setTextColor(if (selected) colors.accentText else colors.foreground)
                gravity = Gravity.CENTER
                maxLines = 1
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(2) })
            setOnClickListener {
                if (!modeRequestPending) {
                    vibrate(this)
                    selectReadingMode(mode)
                }
            }
        }

    private fun selectReadingMode(requestedMode: String) {
        val targetMode = if (requestedMode == readingMode && requestedMode != MODE_NORMAL) MODE_NORMAL else requestedMode
        if ((targetMode == readingMode && receiverMode == targetMode) || modeRequestPending) return
        val previousMode = receiverMode
        modeRequestPending = true
        renderUi()
        val modeData = JSONObject()
            .put("from_mode", previousMode)
            .put("mode", targetMode)
        sendAction("set_mode", extraData = modeData) { succeeded ->
            modeRequestPending = false
            if (succeeded) {
                readingMode = targetMode
                receiverMode = targetMode
                prefs.edit().putString(KEY_READING_MODE, receiverMode).apply()
            }
            renderUi()
        }
    }

    private fun weightButton() = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)

    private fun actionButton(label: String, description: String, colors: Palette, onClick: () -> Unit) = Button(this).apply {
        text = label
        contentDescription = description
        isAllCaps = false
        textSize = 15f
        setTextColor(colors.foreground)
        backgroundTintList = ColorStateList.valueOf(colors.surface)
        setOnClickListener { vibrate(this); onClick() }
    }

    private fun themeIcon(): Int = when (themeMode) {
        THEME_LIGHT -> R.drawable.ic_theme_light
        THEME_DARK -> R.drawable.ic_theme_dark
        else -> R.drawable.ic_theme_auto
    }

    private fun themeDescription(): String = when (themeMode) {
        THEME_LIGHT -> "App theme: Day. Tap to switch to Night."
        THEME_DARK -> "App theme: Night. Tap to switch to Auto."
        else -> "App theme: Auto. Tap to switch to Day."
    }

    private fun vibrate(source: View? = null) {
        val nativeFeedbackPlayed = source?.performHapticFeedback(
            HapticFeedbackConstants.VIRTUAL_KEY,
            HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING,
        ) == true
        if (nativeFeedbackPlayed) return

        val vibrator = getSystemService(Vibrator::class.java) ?: return
        if (!vibrator.hasVibrator()) return
        try {
            vibrator.vibrate(VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE))
        } catch (_: SecurityException) {
            // Native view haptics remain available if direct vibration is restricted.
        }
    }

    private fun addStatusLine(parent: LinearLayout, colors: Palette, initialText: String) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        statusDot = View(this).apply { background = circle(colors.muted) }
        row.addView(statusDot, LinearLayout.LayoutParams(dp(8), dp(8)).apply { marginEnd = dp(8) })
        status = TextView(this).apply {
            text = initialText
            textSize = 13f
            setTextColor(colors.muted)
        }
        row.addView(status, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        parent.addView(row, topMargin(10))
    }

    private fun field(hintText: String, colors: Palette) = EditText(this).apply {
        hint = hintText
        textSize = 14f
        setSingleLine(true)
        setTextColor(colors.foreground)
        setHintTextColor(colors.muted)
        backgroundTintList = ColorStateList.valueOf(colors.outline)
        setPadding(dp(12), dp(7), dp(12), dp(7))
    }

    private fun sectionLabel(textValue: String, colors: Palette) = TextView(this).apply {
        text = textValue
        textSize = 11f
        letterSpacing = 0.08f
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setTextColor(colors.muted)
    }

    private fun card(colors: Palette) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(14), dp(13), dp(14), dp(13))
        background = rounded(colors.surface, colors.outline, 18)
    }

    private fun rounded(fill: Int, stroke: Int, radius: Int) = GradientDrawable().apply {
        setColor(fill)
        cornerRadius = dp(radius).toFloat()
        if (stroke != Color.TRANSPARENT) setStroke(dp(1), stroke)
    }

    private fun circle(fill: Int) = GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(fill)
    }

    private fun matchWrap() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
    )

    private fun topMargin(value: Int) = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
    ).apply { topMargin = dp(value) }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun isLight(color: Int): Boolean = Color.red(color) * 299 + Color.green(color) * 587 + Color.blue(color) * 114 > 150000

    private fun connectionDetails(): Triple<String, Int, String>? {
        val editingConnection = showSettings && ::hostInput.isInitialized &&
            ::portInput.isInitialized && ::tokenInput.isInitialized
        val host = if (editingConnection) hostInput.text.toString().trim()
            else (prefs.getString(KEY_HOST, "") ?: "").trim()
        val portText = if (editingConnection) portInput.text.toString().trim()
            else prefs.getString(KEY_PORT, "") ?: ""
        val port = portText.toIntOrNull()
        val token = if (editingConnection) tokenInput.text.toString() else readStoredSecret()
        if (host.isBlank() || port == null || port !in 1..65535 || token.isBlank()) {
            updateStatus("Enter a valid laptop IP, port, and secret.", palette.danger)
            return null
        }
        return Triple(host, port, token)
    }

    private fun savePairing(showMessage: Boolean): Boolean {
        if (!::hostInput.isInitialized || !::portInput.isInitialized || !::tokenInput.isInitialized) return false
        val host = hostInput.text.toString().trim()
        val portText = portInput.text.toString().trim()
        val port = portText.toIntOrNull()
        val secret = tokenInput.text.toString()
        if (host.isBlank() || port == null || port !in 1..65535 || secret.isBlank()) {
            if (showMessage) updateStatus("Enter a valid IP, port, and secret before saving.", palette.danger)
            return false
        }
        prefs.edit()
            .putString(KEY_HOST, host)
            .putString(KEY_PORT, portText)
            .putString(KEY_SECRET, encryptSecret(secret))
            .apply()
        if (showMessage) updateStatus("Pairing saved securely on this phone.", palette.success)
        return true
    }

    private fun savePairingQuietly() {
        if (::hostInput.isInitialized && ::tokenInput.isInitialized && hostInput.text.isNotBlank() && tokenInput.text.isNotBlank()) {
            val port = portInput.text.toString().toIntOrNull()
            if (port != null && port in 1..65535) savePairing(showMessage = false)
        }
    }

    private fun readStoredSecret(): String = try {
        prefs.getString(KEY_SECRET, null)?.let(::decryptSecret) ?: ""
    } catch (_: Exception) {
        prefs.edit().remove(KEY_SECRET).apply()
        ""
    }

    private fun hasSavedPairing(): Boolean {
        val host = prefs.getString(KEY_HOST, "") ?: ""
        val port = (prefs.getString(KEY_PORT, "") ?: "").toIntOrNull()
        return host.isNotBlank() && port != null && port in 1..65535 && readStoredSecret().isNotBlank()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build())
        return generator.generateKey()
    }

    private fun encryptSecret(value: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return Base64.getEncoder().encodeToString(cipher.iv + encrypted)
    }

    private fun decryptSecret(value: String): String {
        val combined = Base64.getDecoder().decode(value)
        val iv = combined.copyOfRange(0, 12)
        val encrypted = combined.copyOfRange(12, combined.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return String(cipher.doFinal(encrypted), Charsets.UTF_8)
    }

    private fun sendHealthCheck() {
        val details = connectionDetails() ?: return
        savePairing(showMessage = false)
        setBusy(true)
        updateStatus("Checking receiver and secret…", palette.muted)
        executor.execute {
            var conn: HttpURLConnection? = null
            try {
                val (host, port, token) = details
                conn = (URL("http://$host:$port/verify").openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 3000
                    readTimeout = 3000
                    setRequestProperty("X-Remote-Token", token)
                }
                val code = conn.responseCode
                runOnUiThread {
                    setBusy(false)
                    when (code) {
                        200 -> updateStatus("Connected. Receiver and secret are verified.", palette.success)
                        401 -> updateStatus("Receiver reached, but the secret does not match.", palette.danger)
                        else -> updateStatus("Receiver replied with HTTP $code.", palette.danger)
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    setBusy(false)
                    updateStatus(connectionError(e), palette.danger)
                }
            } finally {
                conn?.disconnect()
            }
        }
    }

    private fun sendAction(
        action: String,
        updateStatus: Boolean = true,
        extraData: JSONObject? = null,
        onResult: ((Boolean) -> Unit)? = null,
    ) {
        if (action in setOf("rsvp_previous", "rsvp_next", "rsvp_previous_chapter", "rsvp_next_chapter")) {
            // RSVP captures the arrow keys, so navigation exits the overlay first.
            // Keep the phone's mode indicator aligned with the reader afterward.
            readingMode = MODE_NORMAL
            receiverMode = MODE_NORMAL
            prefs.edit().putString(KEY_READING_MODE, receiverMode).apply()
            renderUi()
        }
        val details = connectionDetails() ?: run {
            onResult?.invoke(false)
            return
        }
        savePairing(showMessage = false)
        if (updateStatus) updateStatus(actionStatus(action), palette.muted)
        executor.execute {
            var conn: HttpURLConnection? = null
            try {
                val (host, port, token) = details
                conn = (URL("http://$host:$port/turn").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 3000
                    readTimeout = 3000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("X-Remote-Token", token)
                }
                val payload = JSONObject().put("action", action)
                extraData?.keys()?.forEach { key -> payload.put(key, extraData.get(key)) }
                val body = payload.toString().toByteArray(Charsets.UTF_8)
                conn.outputStream.use { it.write(body) }
                val code = conn.responseCode
                runOnUiThread {
                    if (updateStatus) {
                        when {
                            code == 200 -> updateStatus(actionSuccess(action), palette.success)
                            code == 401 -> updateStatus("Receiver reached, but the secret does not match.", palette.danger)
                            code == 409 -> updateStatus("Open Readest and focus the reader window, then retry.", palette.danger)
                            code == 400 -> updateStatus("Receiver rejected this action. Restart receiver.py to load the updated controls.", palette.danger)
                            else -> updateStatus("Receiver replied with HTTP $code.", palette.danger)
                        }
                    }
                    onResult?.invoke(code == 200)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    if (updateStatus) updateStatus(connectionError(e), palette.danger)
                    onResult?.invoke(false)
                }
            } finally {
                conn?.disconnect()
            }
        }
    }

    private fun actionStatus(action: String) = when (action) {
        "set_mode" -> "Switching Readest reading mode…"
        "enter_autoscroll" -> "Switching Readest to scrolled Auto Scroll…"
        "autoscroll_to_paragraph" -> "Switching to paragraph reading…"
        "paragraph_to_speed" -> "Starting speed reading…"
        "speed_to_normal" -> "Closing speed reading…"
        "autoscroll_slower" -> "Reducing Auto Scroll speed…"
        "autoscroll_faster" -> "Increasing Auto Scroll speed…"
        "speed_slower" -> "Reducing WPM…"
        "speed_faster" -> "Increasing WPM…"
        "font_smaller" -> "Decreasing Readest font size…"
        "font_larger" -> "Increasing Readest font size…"
        "autoscroll_pause", "speed_pause" -> "Toggling reading playback…"
        "rsvp_previous", "rsvp_next" -> "Turning page in speed reading…"
        "rsvp_previous_chapter", "rsvp_next_chapter" -> "Changing chapter in speed reading…"
        "previous" -> "Turning to previous page…"
        "next" -> "Turning to next page…"
        "previous_chapter" -> "Going to previous chapter…"
        "next_chapter" -> "Going to next chapter…"
        else -> "Changing Readest theme mode…"
    }

    private fun actionSuccess(action: String) = when (action) {
        "set_mode" -> "Readest reading mode updated."
        "enter_autoscroll" -> "Auto Scroll started."
        "autoscroll_to_paragraph" -> "Paragraph reading started."
        "paragraph_to_speed" -> "Speed reading started."
        "speed_to_normal" -> "Speed reading closed."
        "previous" -> "Previous page command sent."
        "next" -> "Next page command sent."
        "previous_chapter" -> "Previous chapter command sent."
        "next_chapter" -> "Next chapter command sent."
        "font_smaller" -> "Readest font size decreased."
        "font_larger" -> "Readest font size increased."
        else -> "Readest theme mode cycled."
    }

    private fun connectionError(error: Exception): String = when (error) {
        is java.net.UnknownHostException -> "Laptop address not found. Check its Wi-Fi IP."
        is java.net.SocketTimeoutException -> "No reply. Check Wi-Fi, receiver, and firewall."
        else -> {
            val host = prefs.getString(KEY_HOST, "") ?: ""
            val port = prefs.getString(KEY_PORT, "18765") ?: "18765"
            "Could not reach $host:$port (${error.javaClass.simpleName}). Check the saved laptop IP, Wi-Fi, and firewall."
        }
    }

    private fun updateStatus(message: String, color: Int) {
        if (::status.isInitialized) {
            status.text = message
            status.setTextColor(color)
            statusDot.background = circle(color)
        }
    }

    private fun setBusy(value: Boolean) {
        busy = value
        if (::saveButton.isInitialized) saveButton.isEnabled = !value
    }

    override fun onPause() {
        savePairingQuietly()
        super.onPause()
    }

    @Deprecated("Use the back gesture to return from connection settings")
    override fun onBackPressed() {
        if (showSettings && hasSavedPairing()) {
            showSettings = false
            renderUi()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        executor.shutdownNow()
        super.onDestroy()
    }

    companion object {
        private const val THEME_AUTO = "auto"
        private const val THEME_LIGHT = "light"
        private const val THEME_DARK = "dark"
        private const val KEY_THEME_MODE = "theme_mode"
        private const val MODE_NORMAL = "normal"
        private const val MODE_AUTOSCROLL = "autoscroll"
        private const val MODE_PARAGRAPH = "paragraph"
        private const val MODE_SPEED = "speed"
        private const val KEY_READING_MODE = "reading_mode"
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val KEY_SECRET = "secret_encrypted"
        private const val KEY_ALIAS = "readest_remote_pairing_key"
    }
}
