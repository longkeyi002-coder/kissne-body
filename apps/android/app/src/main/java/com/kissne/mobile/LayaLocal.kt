package com.kissne.mobile

import android.content.Context
import com.kissne.mobile.laya.LayaEngine
import com.kissne.mobile.laya.LayaJson
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

internal object LayaLocal {
    private data class Asset(val name: String, val bytes: Long, val sha256: String)
    private val assets = listOf(
        Asset("laya_ml_s256_embeds_wfp16.tflite", 250889040L, "712f2fea6b2c39759b4c46274cd83b7653f2539fedc4d7569e4c7bf903894ac8"),
        Asset("laya_ml_act_head_fp32.tflite", 795816L, "30da532a8b752fdc82351740b0194d440a13d342ed77b9f8848978f1a96cf16d"),
        Asset("laya_ml_calibration.json", 9156L, "80e148c68154b607e7bb66446f064b1fe5da649e1074c917b25e02551a566f2c"),
        Asset("tokenizer.json", 34363188L, "609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f"),
        Asset("token_embeddings_fp16.bin", 393216000L, "58608f7bbd72e03adb3e2db8c4942407058eaeaac38e3abec1d6cb01c1512265"),
        Asset("token_embeddings.json", 801L, "8b25844d858ace3833b69354a60536111e9bbcecb2e305bee7971e8dfcbd83ef"),
    )
    private val downloading = AtomicBoolean(false)
    @Volatile private var progress = 0.0
    @Volatile private var completedBytes = 0L
    @Volatile private var failure = ""
    @Volatile private var engine: LayaEngine? = null
    @Volatile private var modelContext: Context? = null

    fun status(context: Context): JSONObject {
        val installed = isInstalled(context)
        return JSONObject()
            .put("supported", true)
            .put("installed", installed)
            .put("downloading", downloading.get())
            .put("progress", progress)
            .put("completed_bytes", completedBytes)
            .put("total_bytes", assets.sumOf { it.bytes })
            .put("error", failure)
    }

    @Synchronized
    fun download(context: Context): JSONObject {
        check(downloading.compareAndSet(false, true)) { "laya_download_in_progress" }
        failure = ""
        progress = 0.0
        completedBytes = 0L
        try {
            val dir = context.applicationContext.filesDir
            val ready = assets.filter { verify(File(dir, it.name), it) }
            completedBytes = ready.sumOf { it.bytes }
            for (asset in assets) {
                val destination = File(dir, asset.name)
                if (verify(destination, asset)) continue
                val temporary = File(dir, asset.name + ".part")
                temporary.delete()
                val connection = (URL("https://huggingface.co/litert-community/Laya-Multilingual-LiteRT/resolve/main/" + asset.name + "?download=true").openConnection() as HttpURLConnection)
                try {
                    connection.connectTimeout = 30000
                    connection.readTimeout = 60000
                    connection.instanceFollowRedirects = true
                    connection.setRequestProperty("User-Agent", "Kissne-Android-Laya/1")
                    check(connection.responseCode in 200..299) { "model_http_" + connection.responseCode }
                    var written = 0L
                    connection.inputStream.use { input ->
                        temporary.outputStream().buffered().use { output ->
                            val buffer = ByteArray(1024 * 256)
                            while (true) {
                                val count = input.read(buffer)
                                if (count < 0) break
                                output.write(buffer, 0, count)
                                written += count
                                progress = ((completedBytes + written).toDouble() / assets.sumOf { it.bytes }).coerceIn(0.0, 1.0)
                            }
                        }
                    }
                    check(written == asset.bytes) { "model_size_mismatch_" + asset.name }
                    check(sha256(temporary) == asset.sha256) { "model_hash_mismatch_" + asset.name }
                    check(temporary.renameTo(destination)) { "model_install_failed_" + asset.name }
                    completedBytes += asset.bytes
                    progress = (completedBytes.toDouble() / assets.sumOf { it.bytes }).coerceIn(0.0, 1.0)
                } finally {
                    connection.disconnect()
                    temporary.delete()
                }
            }
            File(dir, ".kissne-laya-ready").writeText("litert-community/Laya-Multilingual-LiteRT:wfp16:s256:v1")
            progress = 1.0
            return status(context)
        } catch (error: Throwable) {
            failure = error.message ?: "laya_download_failed"
            throw error
        } finally {
            downloading.set(false)
        }
    }

    fun classify(context: Context, text: String): JSONObject {
        val input = text.trim()
        require(input.isNotEmpty()) { "text_required" }
        require(input.length <= 1200) { "text_too_long" }
        check(isInstalled(context)) { "laya_model_not_installed" }
        val started = System.nanoTime()
        val active = synchronized(this) {
            val app = context.applicationContext
            if (engine == null || modelContext !== app) {
                engine?.close()
                modelContext = app
                engine = LayaEngine(app, LayaEngine.Storage.WFP16)
            }
            engine!!
        }
        val question = linkedMapOf<String, Any?>(
            "type" to "choice",
            "instructions" to "判断下面这段内容是否适合作为用户长期记忆候选。只依据内容本身；不适合的内容包括临时状态、一次性请求和缺少长期价值的信息。",
            "criteria" to linkedMapOf(
                "不适合" to "内容短暂、一次性或不值得长期记住",
                "记忆候选" to "稳定偏好、长期事实、重要约定或重复目标",
            ),
        )
        val result = active.answer(input, question, LayaEngine.Backend.CPU, questionId = "kissne_memory_candidate")
        return JSONObject(LayaJson.stringify(linkedMapOf(
            "answer" to result.answer,
            "elapsed_ms" to ((System.nanoTime() - started) / 1_000_000.0).toLong(),
            "local_only" to true,
        )))
    }

    private fun isInstalled(context: Context): Boolean {
        val marker = File(context.applicationContext.filesDir, ".kissne-laya-ready")
        return marker.isFile &&
            assets.all { asset -> File(context.applicationContext.filesDir, asset.name).let { it.isFile && it.length() == asset.bytes } }
    }

    private fun verify(file: File, asset: Asset): Boolean =
        file.isFile && file.length() == asset.bytes && sha256(file) == asset.sha256

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(1024 * 256)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
