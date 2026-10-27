package com.example.readestremote

import java.net.URL
import java.security.MessageDigest
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

internal object PinnedHttp {
    fun open(host: String, port: Int, fingerprint: String, path: String): HttpsURLConnection {
        val expected = fingerprint.lowercase().replace(":", "")
        require(expected.matches(Regex("[0-9a-f]{64}"))) { "Invalid receiver certificate fingerprint" }
        val manager = object : X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                require(chain.isNotEmpty()) { "Receiver did not present a certificate" }
                val actual = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded)
                    .joinToString("") { "%02x".format(it) }
                if (!MessageDigest.isEqual(actual.toByteArray(), expected.toByteArray()))
                    throw java.security.cert.CertificateException("Receiver certificate changed; scan its QR again")
            }
        }
        val context = SSLContext.getInstance("TLS")
        context.init(null, arrayOf<TrustManager>(manager), java.security.SecureRandom())
        return (URL("https://$host:$port$path").openConnection() as HttpsURLConnection).apply {
            sslSocketFactory = context.socketFactory
            hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }
            connectTimeout = 4000
            readTimeout = 4000
        }
    }
}
