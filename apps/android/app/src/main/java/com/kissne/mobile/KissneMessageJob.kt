package com.kissne.mobile

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import java.util.concurrent.Executors

/** Idle background checks do not need a permanent foreground notification. */
class KissneMessageJob : JobService() {
    private val reader = Executors.newSingleThreadExecutor()

    override fun onStartJob(params: JobParameters): Boolean {
        reader.execute {
            try {
                NotificationReplyObserver.poll(this, MobileSessionStore(this))
                jobFinished(params, false)
            } catch (_: Exception) {
                jobFinished(params, true)
            }
        }
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean = true

    override fun onDestroy() {
        reader.shutdownNow()
        super.onDestroy()
    }

    companion object {
        fun schedule(context: Context) {
            val scheduler = context.getSystemService(JobScheduler::class.java)
            if (scheduler.getPendingJob(2109) != null) return
            scheduler.schedule(JobInfo.Builder(2109, ComponentName(context, KissneMessageJob::class.java))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(15 * 60 * 1000L)
                .build())
        }
    }
}
