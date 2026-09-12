# Optional: an alert, not a spending cap — GCP budgets never stop
# resources on their own. Skipped entirely unless billing_account_id is
# set, since Terraform needs Billing Account Administrator on that
# account to manage it, a broader grant than anything else here needs.

resource "google_monitoring_notification_channel" "budget_email" {
  count        = var.billing_account_id != "" && var.alert_notification_email != "" ? 1 : 0
  project      = var.project_id
  display_name = "AI-Ops Agent budget alerts"
  type         = "email"
  labels = {
    email_address = var.alert_notification_email
  }
}

resource "google_billing_budget" "monthly" {
  count           = var.billing_account_id != "" ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "ai-ops-agent-monthly-budget"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    monitoring_notification_channels = (
      var.alert_notification_email != "" ? [google_monitoring_notification_channel.budget_email[0].id] : []
    )
  }
}
