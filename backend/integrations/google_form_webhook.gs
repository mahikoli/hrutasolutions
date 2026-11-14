/**
 * Bound to the master Google response spreadsheet.
 *
 * Script Properties required:
 *   CRM_WEBHOOK_URL    = https://<backend-host>/api/v1/internship-management/sync/google-form-webhook
 *   CRM_WEBHOOK_SECRET = same value as backend GOOGLE_FORM_WEBHOOK_SECRET
 *
 * After setting properties, run installCrmFormSubmitTrigger() once.
 */
function forwardFormSubmissionToCrm(event) {
  if (!event || !event.namedValues || !event.range || !event.source) {
    throw new Error("This function must run from a spreadsheet form-submit trigger.");
  }

  const properties = PropertiesService.getScriptProperties();
  const webhookUrl = properties.getProperty("CRM_WEBHOOK_URL");
  const webhookSecret = properties.getProperty("CRM_WEBHOOK_SECRET");
  if (!webhookUrl || !webhookSecret) {
    throw new Error("Set CRM_WEBHOOK_URL and CRM_WEBHOOK_SECRET in Script Properties first.");
  }

  const sheet = event.range.getSheet();
  const responseId = [event.source.getId(), sheet.getSheetId(), event.range.getRow()].join(":");
  const values = {};
  Object.entries(event.namedValues).forEach(([question, answers]) => {
    values[question] = Array.isArray(answers) ? answers.join(", ") : String(answers ?? "");
  });

  const payload = JSON.stringify({ response_id: responseId, values });
  let lastError = "Unknown webhook error";
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const response = UrlFetchApp.fetch(webhookUrl, {
      method: "post",
      contentType: "application/json",
      headers: { "X-Form-Webhook-Secret": webhookSecret },
      payload,
      muteHttpExceptions: true,
    });
    const status = response.getResponseCode();
    if (status >= 200 && status < 300) {
      console.log(`CRM accepted registration ${responseId}: ${response.getContentText()}`);
      return;
    }

    lastError = `CRM returned ${status}: ${response.getContentText()}`;
    if (status < 500 && status !== 429) break;
    Utilities.sleep(500 * (attempt + 1));
  }
  throw new Error(lastError);
}

function installCrmFormSubmitTrigger() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error("Open this Apps Script project from the master response spreadsheet.");
  }

  const alreadyInstalled = ScriptApp.getProjectTriggers().some((trigger) =>
    trigger.getHandlerFunction() === "forwardFormSubmissionToCrm" &&
    trigger.getEventType() === ScriptApp.EventType.ON_FORM_SUBMIT
  );
  if (!alreadyInstalled) {
    ScriptApp.newTrigger("forwardFormSubmissionToCrm")
      .forSpreadsheet(spreadsheet)
      .onFormSubmit()
      .create();
  }
}
