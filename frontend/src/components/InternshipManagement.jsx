import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Award, BarChart3, CalendarClock, CalendarDays, Check, ChevronDown, CircleDollarSign,
  ClipboardCheck, Download, FileText, GraduationCap, RefreshCw, Search, ShieldCheck,
  UsersRound, UserRound, X,
} from "lucide-react";

const rawApiBase = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1").trim().replace(/\/+$/, "");
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;
const STUDENT_STATUSES = [
  ["new_registration", "New registration"], ["not_contacted", "Not contacted"], ["contacted", "Contacted"],
  ["interested", "Interested"], ["not_interested", "Not interested"], ["follow_up_required", "Follow-up required"],
  ["documents_pending", "Documents pending"], ["payment_pending", "Payment pending"], ["payment_verified", "Payment verified"],
  ["eligible", "Eligible"], ["not_eligible", "Not eligible"], ["ready_for_batch", "Ready for batch"],
  ["batch_assigned", "Batch assigned"], ["dropped_out", "Dropped out"], ["completed", "Completed"],
];
const SECTIONS = [
  ["overview", "Overview", BarChart3], ["students", "Student registrations", UsersRound],
  ["management", "Student management", UsersRound],
  ["followups", "Follow-ups", CalendarClock], ["payments", "Payment verification", CircleDollarSign],
  ["batches", "Batch management", GraduationCap], ["trainers", "Trainer management", UserRound],
  ["sessions", "Training sessions", CalendarDays], ["attendance", "Attendance", ClipboardCheck],
  ["assignments", "Assignments", FileText], ["progress", "Student progress", BarChart3],
  ["evaluations", "Final evaluation", ShieldCheck], ["certificates", "Certificates", Award],
  ["reports", "Reports & analytics", BarChart3], ["settings", "Internship settings", ShieldCheck],
];

async function api(path, token, options = {}) {
  const headers = { Authorization: `Bearer ${token}` };
  if (options.body !== undefined && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET", headers,
      body: options.body === undefined ? undefined : options.body instanceof FormData ? options.body : JSON.stringify(options.body),
    });
  } catch {
    throw new Error(`Could not reach the OneCRM API at ${API_BASE}.`);
  }
  const payload = options.raw ? response : await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`);
  return payload;
}

const money = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0));
const dateText = (value, withTime = false) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("en-IN", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(date);
};
const labelFor = (list, value) => list.find(([key]) => key === value)?.[1] || String(value || "—").replaceAll("_", " ");
const shortName = (name) => String(name || "").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();

const FORM_FIELDS = {
  student: [
    { name: "full_name", label: "Full name", required: true }, { name: "email", label: "Email", type: "email", required: true },
    { name: "phone", label: "Mobile number" }, { name: "whatsapp_number", label: "WhatsApp number" },
    { name: "date_of_birth", label: "Date of birth", type: "date" }, { name: "college_name", label: "College" },
    { name: "university", label: "University" }, { name: "degree", label: "Degree" }, { name: "department", label: "Department" },
    { name: "current_academic_year", label: "Current academic year" }, { name: "graduation_year", label: "Graduation year", type: "number" },
    { name: "selected_domain", label: "Internship domain", required: true }, { name: "preferred_duration_weeks", label: "Preferred duration (weeks)", type: "number" },
    { name: "preferred_mode", label: "Training mode", type: "select", options: [["online", "Online"], ["onsite", "Offline"], ["hybrid", "Hybrid"]] },
    { name: "technical_skills", label: "Technical skills", type: "textarea" }, { name: "previous_experience", label: "Previous experience", type: "textarea" },
    { name: "payment_option", label: "Payment option", type: "select", options: [["pending", "Payment pending"], ["paid", "Paid registration"], ["free", "Free registration"], ["partial", "Partial payment"]] },
    { name: "payment_amount", label: "Registration amount (₹)", type: "number", defaultValue: "0" },
    { name: "registration_source", label: "Registration source", defaultValue: "manual" },
    { name: "internal_remarks", label: "Internal remarks", type: "textarea", wide: true },
  ],
  followup: [
    { name: "outcome", label: "Outcome" }, { name: "follow_up_at", label: "Contacted at", type: "datetime-local" },
    { name: "next_follow_up_at", label: "Next follow-up", type: "datetime-local" },
    { name: "notes", label: "Call notes", type: "textarea", required: true, wide: true },
  ],
  payment: [
    { name: "amount", label: "Amount received (₹)", type: "number", required: true },
    { name: "payment_date", label: "Payment date", type: "date", defaultValue: new Date().toISOString().slice(0, 10) },
    { name: "method", label: "Payment method", defaultValue: "manual" }, { name: "transaction_id", label: "Transaction ID" },
    { name: "receipt_reference", label: "Receipt reference", type: "textarea", wide: true },
  ],
  feedback: [
    { name: "feedback_type", label: "Feedback source", type: "select", options: [["student", "Student satisfaction"], ["trainer", "Trainer feedback"]], defaultValue: "student" },
    { name: "rating", label: "Satisfaction rating (1–5)", type: "number", required: true, min: "1", max: "5" },
    { name: "placement_interest", label: "Interested in placement or further internship?", type: "select", options: [["", "Not recorded"], ["true", "Yes"], ["false", "No"]] },
    { name: "comments", label: "Feedback notes", type: "textarea", wide: true },
  ],
  batch: [
    { name: "name", label: "Batch name", required: true }, { name: "domain", label: "Internship domain", required: true },
    { name: "program_id", label: "Program", type: "select", options: [] }, { name: "duration_weeks", label: "Duration (weeks)", type: "number", required: true },
    { name: "start_date", label: "Start date", type: "date", required: true }, { name: "end_date", label: "End date", type: "date", required: true },
    { name: "capacity", label: "Maximum capacity", type: "number", required: true },
    { name: "coordinator_id", label: "Batch coordinator", type: "select", options: [] },
    { name: "trainer_id", label: "Trainer", type: "select", options: [] },
    { name: "unpaid_approval_required", label: "Require approval for unpaid students", type: "select", options: [["true", "Yes, manager approval"], ["false", "No"]], defaultValue: "true" },
  ],
  trainer: [
    { name: "name", label: "Trainer name", required: true }, { name: "user_id", label: "Linked CRM user", type: "select", options: [] },
    { name: "email", label: "Email", type: "email" }, { name: "phone", label: "Contact number" },
    { name: "expertise", label: "Technical specialization", type: "textarea", wide: true },
    { name: "experience_years", label: "Years of experience", type: "number" },
  ],
  session: [
    { name: "batch_id", label: "Batch", type: "select", options: [], required: true }, { name: "session_number", label: "Session number", type: "number", required: true },
    { name: "title", label: "Session title", required: true }, { name: "topic", label: "Topic" },
    { name: "starts_at", label: "Starts at", type: "datetime-local", required: true }, { name: "ends_at", label: "Ends at", type: "datetime-local" },
    { name: "meeting_url", label: "Meeting link", type: "url" }, { name: "resources", label: "Learning resources", type: "textarea", wide: true },
    { name: "description", label: "Description", type: "textarea", wide: true },
  ],
  assignment: [
    { name: "batch_id", label: "Batch", type: "select", options: [], required: true }, { name: "title", label: "Assignment title", required: true },
    { name: "due_at", label: "Due date", type: "datetime-local" }, { name: "max_score", label: "Maximum score", type: "number", defaultValue: "100" },
    { name: "description", label: "Instructions", type: "textarea", wide: true },
  ],
  submission: [
    { name: "application_id", label: "Student", type: "select", options: [], required: true },
    { name: "submission_link", label: "Project or file link", type: "url" },
    { name: "submission_text", label: "Submission notes", type: "textarea", wide: true },
  ],
};

function FormDialog({ title, fields, onClose, onSubmit, busy, error, submitLabel = "Save record" }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.name, field.defaultValue ?? ""])));
  const [localError, setLocalError] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = {};
    for (const field of fields) {
      let value = form.get(field.name);
      if (field.type === "number") value = value === "" ? null : Number(value);
      else if (field.type === "select" && field.name === "unpaid_approval_required") value = value === "true";
      else if (value === "") value = null;
      result[field.name] = value;
    }
    try { setLocalError(""); await onSubmit(result); }
    catch (reason) { setLocalError(reason.message); }
  };
  return <div className="im-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="im-dialog" role="dialog" aria-modal="true" aria-label={title}>
      <header><div><span className="im-eyebrow">INTERNSHIP MANAGEMENT</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></header>
      <form onSubmit={submit}>
        <div className="im-form-grid">{fields.map((field) => <label key={field.name} className={field.wide ? "im-wide" : ""}>
          <span>{field.label}{field.required && <b> *</b>}</span>
          {field.type === "textarea" ? <textarea name={field.name} required={field.required} value={values[field.name] || ""} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} rows={3} /> :
            field.type === "select" ? <select name={field.name} required={field.required} value={values[field.name] || ""} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}><option value="">Select…</option>{(field.options || []).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select> :
              <input name={field.name} type={field.type || "text"} min={field.min} max={field.max} required={field.required} value={values[field.name] || ""} onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))} />}
        </label>)}</div>
        {(localError || error) && <div className="im-form-error" role="alert">{localError || error}</div>}
        <footer><button type="button" className="soft-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy}>{busy && <span className="button-loader" />}{busy ? "Saving…" : submitLabel}</button></footer>
      </form>
    </section>
  </div>;
}

function Metric({ label, value, note, tone = "blue" }) {
  return <article className={`im-metric im-metric-${tone}`}><span>{label}</span><strong>{value ?? "—"}</strong>{note && <small>{note}</small>}</article>;
}

function ChartBars({ title, rows, labelKey, valueKey }) {
  const max = Math.max(1, ...rows.map((row) => Number(row[valueKey] || 0)));
  return <article className="im-panel"><header><h3>{title}</h3></header>{rows.length ? <div className="im-bars">{rows.map((row, index) => <div className="im-bar" key={`${row[labelKey]}-${index}`}><div><span>{row[labelKey] || "Unspecified"}</span><b>{row[valueKey]}</b></div><i><span style={{ width: `${Math.max(3, Number(row[valueKey] || 0) / max * 100)}%` }} /></i></div>)}</div> : <div className="im-empty">No records yet. This chart will fill from live CRM data.</div>}</article>;
}

function InternshipManagement({ token, user }) {
  const roles = user?.roles || [];
  const manager = roles.some((role) => ["Super Admin", "Management"].includes(role));
  const finance = manager || roles.includes("Finance / Accounts");
  const coordinator = manager || roles.some((role) => ["Internship Coordinator", "Employee / Intern"].includes(role));
  const fullCoordinator = manager || roles.includes("Internship Coordinator");
  const trainerRole = manager || roles.some((role) => ["Internship Coordinator", "Training Coordinator", "Trainer / Teacher"].includes(role));
  const canRecordStudentFeedback = coordinator || roles.includes("Training Coordinator");
  const [section, setSection] = useState("overview");
  const [overview, setOverview] = useState(null);
  const [students, setStudents] = useState({ items: [], total: 0 });
  const [batches, setBatches] = useState([]);
  const [trainers, setTrainers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [certificates, setCertificates] = useState([]);
  const [payments, setPayments] = useState([]);
  const [followups, setFollowups] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [users, setUsers] = useState([]);
  const [config, setConfig] = useState(null);
  const [syncRuns, setSyncRuns] = useState([]);
  const [reports, setReports] = useState(null);
  const [studentSearch, setStudentSearch] = useState("");
  const [studentDomain, setStudentDomain] = useState("");
  const [studentCollege, setStudentCollege] = useState("");
  const [studentStatus, setStudentStatus] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("");
  const [registeredFrom, setRegisteredFrom] = useState("");
  const [registeredTo, setRegisteredTo] = useState("");
  const [studentPage, setStudentPage] = useState(1);
  const [studentProfile, setStudentProfile] = useState(null);
  const [studentProgress, setStudentProgress] = useState(null);
  const [selectedSession, setSelectedSession] = useState("");
  const [selectedBatch, setSelectedBatch] = useState("");
  const [submissionAssignment, setSubmissionAssignment] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [evaluationForm, setEvaluationForm] = useState(null);
  const [form, setForm] = useState("");
  const [formContext, setFormContext] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const financeOnly = finance && !coordinator && !trainerRole;

  useEffect(() => { if (financeOnly) setSection("payments"); }, [financeOnly]);

  const loadStudents = useCallback(async (page = 1) => {
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (studentSearch.trim()) params.set("search", studentSearch.trim());
    if (studentDomain) params.set("domain", studentDomain);
    if (studentCollege.trim()) params.set("college", studentCollege.trim());
    if (studentStatus) params.set("student_status", studentStatus);
    if (paymentFilter) params.set("payment_status", paymentFilter);
    if (registeredFrom) params.set("registered_from", registeredFrom);
    if (registeredTo) params.set("registered_to", registeredTo);
    setStudents(await api(`/internship-management/students?${params}`, token));
  }, [token, studentSearch, studentDomain, studentCollege, studentStatus, paymentFilter, registeredFrom, registeredTo]);

  const refreshData = useCallback(async () => {
    setBusy(true); setError("");
    const tasks = financeOnly ? [["payments", "/internship-management/payments"]] : [
      ["overview", "/internship-management/overview"],
      ["students", `/internship-management/students?page=${studentPage}&page_size=50`],
      ["batches", "/internship-management/batches"], ["trainers", "/internship-management/trainers"],
      ["sessions", "/internship-management/sessions"], ["assignments", "/internship-management/assignments"],
      ["evaluations", "/internship-management/evaluations"], ["certificates", "/internship-management/certificates"],
      ["settings", "/internship-management/settings"], ["reports", "/internship-management/reports"],
    ];
    if (!financeOnly && fullCoordinator) tasks.push(["programs", "/internships/programs"], ["users", "/directory/users"]);
    if (!financeOnly && coordinator) tasks.push(["followups", "/internship-management/followups"]);
    else if (!financeOnly && trainerRole) tasks.push(["followups", "/internship-management/followups"]);
    if (!financeOnly && (finance || coordinator)) tasks.push(["payments", "/internship-management/payments"]);
    if (manager) tasks.push(["syncRuns", "/internship-management/sync/runs"]);
    const results = await Promise.allSettled(tasks.map(([, path]) => api(path, token)));
    const nextError = results.find((result) => result.status === "rejected")?.reason?.message;
    if (nextError) setError(nextError);
    const values = Object.fromEntries(tasks.map(([key], index) => [key, results[index].status === "fulfilled" ? results[index].value : null]));
    if (values.overview) setOverview(values.overview);
    if (values.students) setStudents(values.students);
    if (values.batches) setBatches(values.batches);
    if (values.trainers) setTrainers(values.trainers);
    if (values.sessions) setSessions(values.sessions);
    if (values.assignments) setAssignments(values.assignments);
    if (values.evaluations) setEvaluations(values.evaluations);
    if (values.certificates) setCertificates(values.certificates);
    if (values.programs) setPrograms(values.programs);
    if (values.users) setUsers(values.users);
    if (values.settings) setConfig(values.settings);
    if (values.followups) setFollowups(values.followups);
    if (values.payments) setPayments(values.payments);
    if (values.syncRuns) setSyncRuns(values.syncRuns);
    if (values.reports) setReports(values.reports);
    setBusy(false);
  }, [token, manager, coordinator, fullCoordinator, trainerRole, finance, financeOnly, studentPage]);

  useEffect(() => { refreshData(); }, [refreshData]);
  useEffect(() => {
    if (!token || financeOnly) return;
    const timer = window.setTimeout(() => loadStudents(studentPage).catch((reason) => setError(reason.message)), 250);
    return () => window.clearTimeout(timer);
  }, [token, loadStudents, studentPage, financeOnly]);

  const perform = async (work, success) => {
    setError(""); setMessage(""); setBusy(true);
    try { await work(); if (success) setMessage(success); await refreshData(); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  };

  const openForm = (kind, context = null) => { setError(""); setFormContext(context); setForm(kind); };
  const formFields = useMemo(() => {
    const fields = FORM_FIELDS[form] || [];
    if (form === "batch") return (manager ? fields : fields.filter((field) => field.name !== "coordinator_id")).map((field) => field.name === "program_id" ? { ...field, options: [["", "No linked program"], ...programs.map((item) => [String(item.id), `${item.name}${item.domain ? ` · ${item.domain}` : ""}`])] } : field.name === "coordinator_id" ? { ...field, options: [["", "Assign to me"], ...users.map((item) => [String(item.id), `${item.full_name} · ${item.email}`])] } : field.name === "trainer_id" ? { ...field, options: [["", "Unassigned"], ...trainers.map((item) => [String(item.id), item.name])] } : field);
    if (form === "trainer") return fields.map((field) => field.name === "user_id" ? { ...field, options: [["", "No linked account"], ...users.map((item) => [String(item.id), `${item.full_name} · ${item.email}`])] } : field);
    if (form === "feedback" && !canRecordStudentFeedback) return fields.map((field) => field.name === "feedback_type" ? { ...field, options: [["trainer", "Trainer feedback"]], defaultValue: "trainer" } : field);
    if (["session", "assignment"].includes(form)) return fields.map((field) => field.name === "batch_id" ? { ...field, options: batches.filter((item) => ["confirmed", "in_progress"].includes(item.status)).map((item) => [String(item.id), `${item.name} · ${item.domain}`]) } : field);
    if (form === "submission") return fields.map((field) => field.name === "application_id" ? { ...field, options: (batches.find((item) => item.id === formContext?.batchId)?.students || []).map(({ student }) => [String(student.id), student.full_name]) } : field);
    return fields;
  }, [form, programs, trainers, users, batches, formContext, canRecordStudentFeedback, manager]);

  const submitForm = async (values) => {
    setBusy(true);
    setError("");
    let path = ""; let body = values;
    if (form === "student") path = "/internship-management/students";
    if (form === "followup") path = `/internship-management/students/${formContext.studentId}/followups`;
    if (form === "payment") path = `/internship-management/students/${formContext.studentId}/payments`;
    if (form === "feedback") {
      path = `/internship-management/students/${formContext.studentId}/feedback`;
      body.rating = Number(body.rating);
      body.placement_interest = body.placement_interest === "" ? null : body.placement_interest === "true";
    }
    if (form === "batch") { path = "/internship-management/batches"; if (body.program_id) body.program_id = Number(body.program_id); else body.program_id = null; if (body.coordinator_id) body.coordinator_id = Number(body.coordinator_id); else body.coordinator_id = null; if (body.trainer_id) body.trainer_id = Number(body.trainer_id); else body.trainer_id = null; }
    if (form === "trainer") { path = "/internship-management/trainers"; if (body.user_id) body.user_id = Number(body.user_id); else body.user_id = null; }
    if (form === "session") { const batchId = body.batch_id; delete body.batch_id; path = `/internship-management/batches/${batchId}/sessions`; if (body.trainer_id) body.trainer_id = Number(body.trainer_id); }
    if (form === "assignment") { if (body.batch_id) body.batch_id = Number(body.batch_id); path = "/internship-management/assignments"; }
    if (form === "submission") { body.application_id = Number(body.application_id); path = `/internship-management/assignments/${formContext.assignmentId}/submissions`; }
    if (body.follow_up_at) body.follow_up_at = new Date(body.follow_up_at).toISOString();
    if (body.next_follow_up_at) body.next_follow_up_at = new Date(body.next_follow_up_at).toISOString();
    if (body.starts_at) body.starts_at = new Date(body.starts_at).toISOString();
    if (body.ends_at) body.ends_at = new Date(body.ends_at).toISOString();
    if (body.due_at) body.due_at = new Date(body.due_at).toISOString();
    try {
      await api(path, token, { method: "POST", body });
      setForm(""); setFormContext(null); setMessage("Saved successfully.");
      await refreshData();
      await loadStudents(studentPage);
      if (form === "feedback") await openStudent(formContext.studentId);
    } finally { setBusy(false); }
  };

  const openStudent = async (id) => {
    setBusy(true); setError("");
    try {
      const [profile, progress] = await Promise.all([
        api(`/internship-management/students/${id}`, token), api(`/internship-management/progress/${id}`, token),
      ]);
      setStudentProfile(profile); setStudentProgress(progress);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  };

  const updateStudent = (id, changes) => perform(async () => {
    await api(`/internship-management/students/${id}`, token, { method: "PATCH", body: changes });
    if (studentProfile?.student?.id === id) await openStudent(id);
    await loadStudents(studentPage);
  }, "Student record updated.");

  const uploadDocument = async (event) => {
    event.preventDefault();
    const file = event.currentTarget.elements.document.files[0];
    if (!file || !studentProfile) return;
    const formData = new FormData(); formData.append("entity_type", "application");
    formData.append("entity_id", String(studentProfile.student.id)); formData.append("file", file);
    await perform(async () => {
      await api("/documents", token, { method: "POST", body: formData });
      await openStudent(studentProfile.student.id);
    }, "Document uploaded securely.");
  };

  const markPayment = (paymentId, approved) => perform(() => api(`/internship-management/payments/${paymentId}/verify?approved=${approved}`, token, { method: "PATCH" }), approved ? "Payment verified." : "Payment rejected.");

  const addStudentsToBatch = (batchId) => {
    const selected = Array.from(document.querySelectorAll(`[data-batch='${batchId}'] option:checked`)).map((item) => Number(item.value));
    if (!selected.length) { setError("Select at least one eligible student first."); return; }
    perform(() => api(`/internship-management/batches/${batchId}/students`, token, { method: "POST", body: selected }), "Students added to batch.");
  };

  const batchAction = (batch, action) => {
    const promptText = action === "cancel" ? "Cancel this internship batch?" : action === "confirm" ? "Confirm the selected batch roster?" : action === "approve" ? "Approve this batch with unpaid students?" : `Mark ${batch.name} as ${action.replaceAll("_", " ")}?`;
    if (!window.confirm(promptText)) return;
    const path = action === "confirm" ? `/internship-management/batches/${batch.id}/confirm` : action === "approve" ? `/internship-management/batches/${batch.id}/approve` : `/internship-management/batches/${batch.id}/transition`;
    perform(() => api(path, token, { method: "POST", body: action === "confirm" || action === "approve" ? {} : { status: action } }), "Batch updated.");
  };

  const setAttendance = (session, student, status) => perform(() => api("/internship-management/attendance", token, { method: "POST", body: { session_id: session.id, application_id: student.id, status } }), "Attendance saved.");

  const showSubmissions = async (assignment) => {
    try { setSubmissions(await api(`/internship-management/assignments/${assignment.id}/submissions`, token)); setSubmissionAssignment(assignment); }
    catch (reason) { setError(reason.message); }
  };

  const reviewSubmission = (row, status) => {
    const score = status === "evaluated" ? window.prompt("Score for this submission", "80") : null;
    if (status === "evaluated" && (score === null || score.trim() === "")) return;
    const feedback = window.prompt("Feedback for the student", "");
    perform(() => api(`/internship-management/submissions/${row.id}/review`, token, { method: "PATCH", body: { status, score: score === null ? null : Number(score), feedback } }), "Submission reviewed.");
  };

  const openEvaluation = (batch) => setEvaluationForm({ batchId: batch.id, studentId: "", criterionScores: Object.fromEntries(Object.keys(config?.evaluation_weights || {}).map((key) => [key, ""])) , feedback: "", project: "", completionDate: "" });
  const saveEvaluation = () => perform(async () => {
    const scores = Object.fromEntries(Object.entries(evaluationForm.criterionScores).filter(([, value]) => value !== "").map(([key, value]) => [key, Number(value)]));
    await api("/internship-management/evaluations", token, { method: "POST", body: {
      batch_id: evaluationForm.batchId, application_id: Number(evaluationForm.studentId), criterion_scores: scores,
      trainer_feedback: evaluationForm.feedback, final_project_details: evaluationForm.project,
      completion_date: evaluationForm.completionDate || null,
    } });
    setEvaluationForm(null);
  }, "Final evaluation submitted for approval.");

  const approveEvaluation = (row, approved) => {
    const admin_remarks = window.prompt(approved ? "Approval remarks" : "What needs to be improved?", "");
    if (admin_remarks === null) return;
    perform(() => api(`/internship-management/evaluations/${row.id}/approval`, token, { method: "PATCH", body: { approved, admin_remarks } }), approved ? "Evaluation approved." : "Evaluation returned for re-evaluation.");
  };

  const generateCertificate = (row) => perform(() => api(`/internship-management/evaluations/${row.id}/certificate`, token, { method: "POST", body: {} }), "Certificate issued.");
  const printCertificate = async (certificate) => {
    try {
      const response = await api(`/internship-management/certificates/${certificate.id}/render`, token, { raw: true });
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (reason) { setError(reason.message); }
  };

  const syncNow = () => perform(async () => {
    const result = await api("/internship-management/sync/google-sheets", token, { method: "POST", body: {} });
    setMessage(`Google Sheets sync complete: ${result.imported} new registrations, ${result.duplicates} existing records.`);
  }, "Google Sheets synchronization complete.");

  const exportStudents = async () => {
    try {
      const response = await api("/internship-management/export/students.csv", token, { raw: true });
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "internship-students.csv"; link.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason.message); }
  };

  const saveSettings = (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const weights = Object.fromEntries(Object.keys(config?.evaluation_weights || {}).map((key) => [key, Number(formData.get(`weight-${key}`) || 0)]));
    const body = { attendance_threshold: Number(formData.get("attendance_threshold")), passing_score: Number(formData.get("passing_score")),
      unpaid_batch_approval_required: formData.get("unpaid_batch_approval_required") === "true", evaluation_weights: weights };
    perform(() => api("/internship-management/settings", token, { method: "PUT", body }), "Internship settings saved.");
  };

  const bulkStatus = (ids, status) => perform(async () => {
    await api("/internship-management/students/bulk-status", token, { method: "POST", body: { student_ids: ids, student_status: status } });
    await loadStudents(studentPage);
    setMessage(`${ids.length} student records updated.`);
  });

  const sectionTitle = SECTIONS.find(([key]) => key === section)?.[1] || "Overview";
  const sectionIsStudents = section === "students" || section === "management";

  const visibleSections = financeOnly ? SECTIONS.filter(([key]) => key === "payments") : SECTIONS;
  return <div className="im-shell">
    <aside className="im-nav"><div className="im-nav-head"><span className="im-nav-mark"><GraduationCap size={18} /></span><div><strong>Internship</strong><small>Lifecycle workspace</small></div></div>
      {visibleSections.map(([key, label, Icon]) => <button key={key} className={section === key ? "active" : ""} onClick={() => { setSection(key); setError(""); }}><Icon size={16} /><span>{label}</span></button>)}
    </aside>
    <main className="im-main">
      <header className="im-page-head"><div><span className="im-eyebrow">INTERNSHIP MANAGEMENT / {sectionTitle.toUpperCase()}</span><h1>{sectionTitle}</h1><p>Manage the student journey from first registration through internship completion.</p></div>
        <div className="im-head-actions">{manager && <button className="soft-button" onClick={syncNow} disabled={busy}><RefreshCw size={15} />Sync Google Forms</button>}{sectionIsStudents && <button className="soft-button" onClick={exportStudents}><Download size={15} />Export for Excel</button>}{coordinator && section === "students" && <button className="primary-button" onClick={() => openForm("student")}>+ Register student</button>}<button className="icon-button" onClick={refreshData} disabled={busy} title="Refresh data"><RefreshCw size={16} className={busy ? "spin-icon" : ""} /></button></div>
      </header>
      {error && <div className="im-alert im-alert-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label="Dismiss error"><X size={15} /></button></div>}
      {message && <div className="im-alert im-alert-success" role="status"><Check size={15} /><span>{message}</span><button onClick={() => setMessage("")} aria-label="Dismiss message"><X size={15} /></button></div>}

      {section === "overview" && <OverviewSection overview={overview} busy={busy} />}
      {sectionIsStudents && <StudentsSection students={students} busy={busy} search={studentSearch} setSearch={setStudentSearch} domain={studentDomain} setDomain={(value) => { setStudentPage(1); setStudentDomain(value); }} domains={(overview?.domain_distribution || []).map((row) => row.domain).filter((value) => value !== "Unspecified")} college={studentCollege} setCollege={(value) => { setStudentPage(1); setStudentCollege(value); }} registeredFrom={registeredFrom} setRegisteredFrom={(value) => { setStudentPage(1); setRegisteredFrom(value); }} registeredTo={registeredTo} setRegisteredTo={(value) => { setStudentPage(1); setRegisteredTo(value); }} status={studentStatus} setStatus={(value) => { setStudentPage(1); setStudentStatus(value); }} payment={paymentFilter} setPayment={(value) => { setStudentPage(1); setPaymentFilter(value); }} page={studentPage} setPage={setStudentPage} users={users} manager={manager} coordinator={coordinator} currentUserId={user.id} management={section === "management"} onProfile={openStudent} onStatus={(id, value) => updateStudent(id, { student_status: value })} onAssign={(id, value) => updateStudent(id, { coordinator_id: value ? Number(value) : null })} onBulkStatus={bulkStatus} />}
      {section === "followups" && <FollowupsSection rows={followups} students={students.items} onAdd={coordinator ? (row) => openForm("followup", { studentId: row.id }) : null} onProfile={openStudent} />}
      {section === "payments" && <PaymentsSection rows={payments} students={students.items} canVerify={finance} onVerify={markPayment} />}
      {section === "batches" && <BatchesSection rows={batches} students={students.items} trainers={trainers} onCreate={coordinator ? () => openForm("batch") : null} onAdd={addStudentsToBatch} onAction={batchAction} onTrainer={(batchId, trainerId) => perform(() => api(`/internship-management/batches/${batchId}/trainer`, token, { method: "PATCH", body: { trainer_id: trainerId ? Number(trainerId) : null } }), "Trainer assignment updated.")} manager={manager} coordinator={coordinator} />}
      {section === "trainers" && <TrainersSection rows={trainers} onCreate={manager ? () => openForm("trainer") : null} onAvailability={manager ? (trainerId, availability) => perform(() => api(`/internship-management/trainers/${trainerId}`, token, { method: "PATCH", body: { availability } }), "Trainer availability updated.") : null} batches={batches} />}
      {section === "sessions" && <SessionsSection rows={sessions} batches={batches} onCreate={trainerRole ? () => openForm("session") : null} onUpdate={trainerRole ? (row, status) => perform(() => api(`/internship-management/sessions/${row.id}`, token, { method: "PATCH", body: { status } }), "Session status updated.") : null} />}
      {section === "attendance" && <AttendanceSection sessions={sessions} batches={batches} selected={selectedSession} setSelected={setSelectedSession} canMark={trainerRole} onMark={setAttendance} />}
      {section === "assignments" && <AssignmentsSection rows={assignments} batches={batches} students={students.items} onCreate={trainerRole ? () => openForm("assignment") : null} onSubmissions={trainerRole ? showSubmissions : null} onSubmit={coordinator ? (assignment, batchId) => openForm("submission", { assignmentId: assignment.id, batchId }) : null} />}
      {section === "progress" && <ProgressSection rows={students.items} selected={studentProgress} selectedId={selectedBatch} setSelectedId={setSelectedBatch} onSelect={async (id) => { setSelectedBatch(String(id)); try { setStudentProgress(await api(`/internship-management/progress/${id}`, token)); } catch (reason) { setError(reason.message); } }} />}
      {section === "evaluations" && <EvaluationsSection rows={evaluations} batches={batches} users={users} manager={manager} onSubmit={trainerRole ? openEvaluation : null} onApprove={approveEvaluation} onCertificate={generateCertificate} />}
      {section === "certificates" && <CertificatesSection rows={certificates} students={students.items} onPrint={printCertificate} />}
      {section === "reports" && <ReportsSection overview={overview} reports={reports} batches={batches} syncRuns={syncRuns} onExport={exportStudents} />}
      {section === "settings" && <SettingsSection config={config} manager={manager} onSave={saveSettings} />}
    </main>

    {form && <FormDialog key={form} title={{ student: "Register a student", followup: `Log a follow-up · Student #${formContext?.studentId}`, payment: `Record payment · Student #${formContext?.studentId}`, feedback: `Record internship feedback · Student #${formContext?.studentId}`, batch: "Create an internship batch", trainer: "Add a trainer", session: "Schedule a training session", assignment: "Create a batch assignment", submission: `Record submission · ${submissionAssignment?.title || "Assignment"}` }[form]}
      fields={formFields} busy={busy} onClose={() => { setForm(""); setFormContext(null); }} onSubmit={submitForm} />}
    {studentProfile && <StudentProfile profile={studentProfile} progress={studentProgress} users={users} manager={manager} coordinator={coordinator} trainerRole={trainerRole} canRecordStudentFeedback={canRecordStudentFeedback} currentUserId={user.id} onClose={() => setStudentProfile(null)} onUpdate={(id, changes) => updateStudent(id, changes)} onForm={openForm} onUpload={uploadDocument} />}
    {submissionAssignment && <SubmissionsDialog assignment={submissionAssignment} rows={submissions} students={students.items} onClose={() => setSubmissionAssignment(null)} onReview={reviewSubmission} />}
    {evaluationForm && <EvaluationDialog form={evaluationForm} setForm={setEvaluationForm} batches={batches} config={config} students={students.items} busy={busy} onClose={() => setEvaluationForm(null)} onSave={saveEvaluation} />}
  </div>;
}

function OverviewSection({ overview, busy }) {
  if (!overview && busy) return <div className="im-loading"><span className="button-loader" />Loading internship data…</div>;
  if (!overview) return <div className="im-empty">Internship summary is unavailable. Refresh to retry.</div>;
  const metrics = [
    ["Total registrations", overview.total_registrations, "All active student records", "blue"],
    ["New registrations", overview.new_registrations, "Needs first contact", "violet"],
    ["Students contacted", overview.students_contacted, "Contact and follow-up status", "cyan"],
    ["Interested students", overview.interested_students, "Counselling pipeline", "green"],
    ["Eligible students", overview.eligible_students, "Ready for batch selection", "blue"],
    ["Paid students", overview.paid_students, "Verified payments", "green"],
    ["Unpaid students", overview.unpaid_students, "Payment checks pending", "cyan"],
    ["Confirmed batches", overview.confirmed_batches, `${overview.active_batches || 0} in progress`, "violet"],
    ["Active interns", overview.active_interns, "Enrolled in active batches", "blue"],
    ["Completed internships", overview.completed_internships, "From student status records", "cyan"],
  ];
  return <>
    <div className="im-metrics">{metrics.map(([label, value, note, tone]) => <Metric key={label} label={label} value={value} note={note} tone={tone} />)}</div>
    <div className="im-overview-grid"><ChartBars title="Student lifecycle" rows={overview.status_distribution || []} labelKey="status" valueKey="count" />
      <ChartBars title="Payment status" rows={overview.payment_distribution || []} labelKey="status" valueKey="count" />
      <ChartBars title="Registrations by domain" rows={overview.domain_distribution || []} labelKey="domain" valueKey="count" />
      <article className="im-panel"><header><h3>Upcoming follow-ups</h3><span>{overview.upcoming_followups?.length || 0} due soon</span></header>{overview.upcoming_followups?.length ? <div className="im-compact-list">{overview.upcoming_followups.map((row) => <div key={row.id}><span className="im-avatar">{shortName(row.full_name)}</span><div><strong>{row.full_name}</strong><small>{dateText(row.next_follow_up_at, true)} · {row.phone || row.email}</small></div><em>{row.student_status.replaceAll("_", " ")}</em></div>)}</div> : <div className="im-empty">No follow-ups due in the next seven days.</div>}</article>
      <article className="im-panel"><header><h3>Pending payment checks</h3><span>{overview.pending_payment_verification?.length || 0} students</span></header>{overview.pending_payment_verification?.length ? <div className="im-compact-list">{overview.pending_payment_verification.map((row) => <div key={row.id}><span className="im-avatar">{shortName(row.full_name)}</span><div><strong>{row.full_name}</strong><small>{row.selected_domain || "Internship"} · {money(row.payment_amount)}</small></div><em>{row.payment_status}</em></div>)}</div> : <div className="im-empty">No payment verification is waiting.</div>}</article>
      <article className="im-panel"><header><h3>Pending batch approvals</h3><span>{overview.pending_batch_approvals || 0} batches</span></header>{overview.pending_batch_approvals ? <p>{overview.pending_batch_approvals} roster(s) with unpaid registrations need an authorized manager's approval.</p> : <div className="im-empty">No unpaid batch approvals are waiting.</div>}</article>
      <article className="im-panel"><header><h3>Upcoming training</h3><span>{overview.upcoming_sessions?.length || 0} sessions</span></header>{overview.upcoming_sessions?.length ? <div className="im-compact-list">{overview.upcoming_sessions.map((row) => <div key={row.id}><span className="im-icon-box"><CalendarDays size={16} /></span><div><strong>{row.title}</strong><small>{dateText(row.starts_at, true)} · Batch #{row.batch_id}</small></div><em>{row.status}</em></div>)}</div> : <div className="im-empty">No future sessions are scheduled.</div>}</article>
      <article className="im-panel"><header><h3>Low attendance</h3><span>{overview.low_attendance_students?.length || 0} alerts</span></header>{overview.low_attendance_students?.length ? <div className="im-compact-list">{overview.low_attendance_students.map(({ student, attendance_percent }) => <div key={student.id}><span className="im-avatar">{shortName(student.full_name)}</span><div><strong>{student.full_name}</strong><small>{student.selected_domain || "Internship"}</small></div><em>{attendance_percent}%</em></div>)}</div> : <div className="im-empty">No student is below the configured attendance threshold.</div>}</article>
      <article className="im-panel"><header><h3>Overdue assignments</h3><span>{overview.missing_assignments?.length || 0} alerts</span></header>{overview.missing_assignments?.length ? <div className="im-compact-list">{overview.missing_assignments.map(({ student, assignment }) => <div key={`${student.id}-${assignment.id}`}><span className="im-avatar">{shortName(student.full_name)}</span><div><strong>{student.full_name}</strong><small>{assignment.title} · Due {dateText(assignment.due_at)}</small></div><em>overdue</em></div>)}</div> : <div className="im-empty">No overdue assignment submissions.</div>}</article>
      <article className="im-panel"><header><h3>Assignments awaiting review</h3><span>{overview.pending_assignment_reviews?.length || 0} submissions</span></header>{overview.pending_assignment_reviews?.length ? <div className="im-compact-list">{overview.pending_assignment_reviews.map((row) => <div key={row.id}><span className="im-icon-box"><FileText size={15} /></span><div><strong>Student #{row.application_id}</strong><small>Assignment #{row.assignment_id} · {row.status.replaceAll("_", " ")}</small></div><em>{dateText(row.submitted_at)}</em></div>)}</div> : <div className="im-empty">No assignment submissions are waiting for review.</div>}</article>
      <article className="im-panel"><header><h3>Inactive students</h3><span>{overview.inactive_students?.length || 0} alerts</span></header>{overview.inactive_students?.length ? <div className="im-compact-list">{overview.inactive_students.map(({ student, last_attendance }) => <div key={student.id}><span className="im-avatar">{shortName(student.full_name)}</span><div><strong>{student.full_name}</strong><small>Last attendance {dateText(last_attendance)}</small></div><em>check in</em></div>)}</div> : <div className="im-empty">No active student has missed attendance for 14 days.</div>}</article>
      <article className="im-panel"><header><h3>Needs performance support</h3><span>{overview.poor_performance_students?.length || 0} students</span></header>{overview.poor_performance_students?.length ? <div className="im-compact-list">{overview.poor_performance_students.map((row) => <div key={row.id}><span className="im-avatar">#{row.application_id}</span><div><strong>Student #{row.application_id}</strong><small>Evaluation · {row.result.replaceAll("_", " ")}</small></div><em>{row.performance_score}%</em></div>)}</div> : <div className="im-empty">No final evaluation is below the passing score.</div>}</article>
    </div>
  </>;
}

function StudentsSection({ students, busy, search, setSearch, domain, setDomain, domains, college, setCollege, registeredFrom, setRegisteredFrom, registeredTo, setRegisteredTo, status, setStatus, payment, setPayment, page, setPage, users, manager, coordinator, currentUserId, management, onProfile, onStatus, onAssign, onBulkStatus }) {
  const rows = students.items || [];
  const [sortBy, setSortBy] = useState("applied_at");
  const [sortDirection, setSortDirection] = useState("desc");
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkStatusValue, setBulkStatusValue] = useState("eligible");
  const sortedRows = useMemo(() => [...rows].sort((left, right) => {
    const a = String(left[sortBy] || "").toLowerCase(); const b = String(right[sortBy] || "").toLowerCase();
    return (a > b ? 1 : a < b ? -1 : 0) * (sortDirection === "asc" ? 1 : -1);
  }), [rows, sortBy, sortDirection]);
  const toggleSort = (key) => { if (sortBy === key) setSortDirection((current) => current === "asc" ? "desc" : "asc"); else { setSortBy(key); setSortDirection("asc"); } };
  return <>
    <div className="im-toolbar"><label className="im-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, email, mobile, college or domain" /></label>
      <select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">All domains</option>{domains.map((value) => <option key={value} value={value}>{value}</option>)}</select>
      <input className="im-date-filter" type="date" aria-label="Registered from" value={registeredFrom} onChange={(event) => setRegisteredFrom(event.target.value)} />
      <input className="im-date-filter" type="date" aria-label="Registered to" value={registeredTo} onChange={(event) => setRegisteredTo(event.target.value)} />
      <input className="im-college-filter" value={college} onChange={(event) => setCollege(event.target.value)} placeholder="College filter" />
      <select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All student statuses</option>{STUDENT_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      <select value={payment} onChange={(event) => setPayment(event.target.value)}><option value="">All payment states</option>{["pending", "partial", "paid", "free", "rejected"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
      <span className="im-count">{students.total || 0} students</span>
    </div>
    {management && coordinator && <div className="im-bulk-toolbar"><span>{selectedIds.length} selected</span><button className="soft-button compact" onClick={() => setSelectedIds(rows.map((row) => row.id))}>Select this page</button><button className="soft-button compact" onClick={() => setSelectedIds([])}>Clear selection</button><select aria-label="Bulk status" value={bulkStatusValue} onChange={(event) => setBulkStatusValue(event.target.value)}>{STUDENT_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><button className="primary-button" disabled={!selectedIds.length || busy} onClick={async () => { await onBulkStatus(selectedIds, bulkStatusValue); setSelectedIds([]); }}>Update selected status</button></div>}
    <div className="im-table-wrap"><table className="im-table"><thead><tr>{management && coordinator && <th scope="col">Select</th>}<th><button className="im-sort" onClick={() => toggleSort("full_name")}>Student {sortBy === "full_name" ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}</button></th><th>College</th><th>Domain</th><th><button className="im-sort" onClick={() => toggleSort("applied_at")}>Registered {sortBy === "applied_at" ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}</button></th><th>Payment</th><th>Assigned employee</th><th>Status</th><th>Next follow-up</th><th /></tr></thead><tbody>
      {sortedRows.map((row) => <tr key={row.id}>{management && coordinator && <td><input type="checkbox" aria-label={`Select ${row.full_name}`} checked={selectedIds.includes(row.id)} onChange={(event) => setSelectedIds((current) => event.target.checked ? [...new Set([...current, row.id])] : current.filter((id) => id !== row.id))} /></td>}<td><button className="im-person-link" onClick={() => onProfile(row.id)}><span className="im-avatar">{shortName(row.full_name)}</span><span><strong>{row.full_name}</strong><small>{row.email}<br />{row.phone || "No mobile number"}</small></span></button></td>
        <td>{row.college_name || "—"}</td><td>{row.selected_domain || "—"}</td><td>{dateText(row.applied_at)}</td>
        <td><span className={`im-pill im-pill-${row.payment_status}`}>{row.payment_status}</span></td>
        <td>{manager ? <select aria-label={`Assign ${row.full_name}`} value={row.coordinator_id || ""} onChange={(event) => onAssign(row.id, event.target.value)}><option value="">Unassigned</option>{users.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select> : row.coordinator_id ? (users.find((person) => person.id === row.coordinator_id)?.full_name || `Employee #${row.coordinator_id}`) : coordinator ? <button className="soft-button compact" onClick={() => onAssign(row.id, currentUserId)}>Assign to me</button> : "Unassigned"}</td>
        <td><select className="im-status-select" disabled={!coordinator} value={row.student_status} onChange={(event) => onStatus(row.id, event.target.value)}>{STUDENT_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></td>
        <td>{dateText(row.next_follow_up_at, true)}</td><td><button className="soft-button compact" onClick={() => onProfile(row.id)}>View profile</button></td></tr>)}
      {!rows.length && <tr><td colSpan={management && coordinator ? "10" : "9"}><div className="im-empty">{busy ? "Loading students…" : "No student registrations match these filters."}</div></td></tr>}
    </tbody></table></div>
    <div className="im-pagination"><span>Page {page} of {Math.max(1, Math.ceil((students.total || 0) / 50))}</span><div><button className="soft-button compact" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="soft-button compact" disabled={page * 50 >= students.total} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
  </>;
}

function FollowupsSection({ rows, students, onAdd, onProfile }) {
  return <div className="im-panel"><header><div><h3>Student follow-up history</h3><small>Call notes, outcomes and next contact dates</small></div></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Student ID</th><th>Contacted</th><th>Outcome</th><th>Notes</th><th>Next follow-up</th><th>Action</th></tr></thead><tbody>{rows.map((row) => { const student = students.find((item) => item.id === row.application_id); return <tr key={row.id}><td><button className="im-person-link" onClick={() => student && onProfile(student.id)}>{student?.full_name || `Student #${row.application_id}`}</button></td><td>{dateText(row.follow_up_at, true)}</td><td>{row.outcome || "—"}</td><td className="im-wrap-cell">{row.notes}</td><td>{dateText(row.next_follow_up_at, true)}</td><td>{student && onAdd && <button className="soft-button compact" onClick={() => onAdd(student)}>Log follow-up</button>}</td></tr>; })}{!rows.length && <tr><td colSpan="6"><div className="im-empty">No follow-up history yet. Open a student profile to add call notes and reminders.</div></td></tr>}</tbody></table></div></div>;
}

function PaymentsSection({ rows, students, canVerify, onVerify }) {
  return <div className="im-panel"><header><div><h3>Payment verification</h3><small>Amounts remain pending until an authorized finance user verifies them.</small></div></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Student</th><th>Amount</th><th>Date</th><th>Method</th><th>Transaction ID</th><th>Receipt reference</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.map((row) => { const student = students.find((item) => item.id === row.application_id); return <tr key={row.id}><td>{student?.full_name || `Student #${row.application_id}`}</td><td>{money(row.amount)}</td><td>{dateText(row.payment_date)}</td><td>{row.method}</td><td>{row.transaction_id || "—"}</td><td>{row.receipt_reference || "—"}</td><td><span className={`im-pill im-pill-${row.status}`}>{row.status}</span></td><td>{canVerify && row.status === "pending" ? <div className="im-actions"><button className="soft-button compact" onClick={() => onVerify(row.id, true)}>Verify</button><button className="soft-button compact danger" onClick={() => onVerify(row.id, false)}>Reject</button></div> : "—"}</td></tr>; })}{!rows.length && <tr><td colSpan="8"><div className="im-empty">No payments are waiting for verification.</div></td></tr>}</tbody></table></div></div>;
}

function BatchesSection({ rows, students, trainers, onCreate, onAdd, onAction, onTrainer, manager, coordinator }) {
  const eligible = students.filter((student) => ["eligible", "ready_for_batch"].includes(student.student_status));
  return <>
    <div className="im-panel im-batch-create"><div><h3>Internship cohorts</h3><p>Build a roster from eligible students. Confirmed rosters are locked.</p></div>{onCreate && <button className="primary-button" onClick={onCreate}>+ Create batch</button>}</div>
    <div className="im-batch-grid">{rows.map((batch) => <article className="im-batch-card" key={batch.id}>
      <header><div><span className="im-eyebrow">{batch.domain}</span><h3>{batch.name}</h3></div><span className={`im-pill im-pill-${batch.status}`}>{batch.status.replaceAll("_", " ")}</span></header>
      <div className="im-batch-meta"><span>{dateText(batch.start_date)} – {dateText(batch.end_date)}</span><span>{batch.duration_weeks} weeks</span><span>Trainer: {batch.trainer_name || "Unassigned"}</span></div>
      {manager && !["completed", "cancelled"].includes(batch.status) && <label className="im-trainer-assignment"><span>Reassign trainer</span><select value={batch.trainer_id || ""} onChange={(event) => onTrainer(batch.id, event.target.value)}><option value="">Unassigned</option>{trainers.map((trainer) => <option key={trainer.id} value={trainer.id} disabled={trainer.availability === "unavailable"}>{trainer.name} · {trainer.availability || "available"}</option>)}</select></label>}
      <div className="im-capacity"><div><span>Roster</span><strong>{batch.student_count} / {batch.capacity}</strong></div><i><span style={{ width: `${Math.min(100, batch.student_count / Math.max(1, batch.capacity) * 100)}%` }} /></i><small>{batch.available_capacity} places available</small></div>
      <div className="im-roster">{(batch.students || []).map(({ student }) => <div key={student.id}><span className="im-avatar">{shortName(student.full_name)}</span><span>{student.full_name}<small>{student.payment_status}</small></span><span className={`im-pill im-pill-${student.payment_status}`}>{student.payment_status}</span></div>)}{!batch.students?.length && <small>No students selected yet.</small>}</div>
      {coordinator && ["draft", "student_selection"].includes(batch.status) && <div className="im-add-roster" data-batch={batch.id}><label><span>Add eligible students for {batch.domain}</span><select multiple size={Math.min(5, Math.max(2, eligible.filter((student) => !student.selected_domain || student.selected_domain.toLowerCase() === batch.domain.toLowerCase()).length))}>{eligible.filter((student) => !student.selected_domain || student.selected_domain.toLowerCase() === batch.domain.toLowerCase()).map((student) => <option key={student.id} value={student.id}>{student.full_name} · {student.payment_status}</option>)}</select></label><button className="soft-button compact" onClick={() => onAdd(batch.id)}>Add selected</button></div>}
      <footer>{["draft", "student_selection"].includes(batch.status) && <button className="primary-button" onClick={() => onAction(batch, "confirm")}>Confirm roster</button>}{batch.status === "pending_approval" && manager && <button className="primary-button" onClick={() => onAction(batch, "approve")}>Approve unpaid students</button>}{batch.status === "confirmed" && (manager || coordinator) && <button className="soft-button" onClick={() => onAction(batch, "in_progress")}>Start batch</button>}{batch.status === "in_progress" && manager && <button className="soft-button" onClick={() => onAction(batch, "completed")}>Complete batch</button>}{["draft", "student_selection", "pending_approval", "confirmed", "in_progress"].includes(batch.status) && <button className="soft-button danger" onClick={() => onAction(batch, "cancelled")}>Cancel</button>}</footer>
    </article>)}{!rows.length && <div className="im-empty im-panel">No batches have been created.</div>}</div>
  </>;
}

function TrainersSection({ rows, onCreate, onAvailability, batches }) {
  return <><div className="im-panel im-section-toolbar"><div><h3>Trainer directory</h3><p>Specializations, availability and workload from current batch assignments.</p></div>{onCreate && <button className="primary-button" onClick={onCreate}>+ Add trainer</button>}</div><div className="im-trainer-grid">{rows.map((row) => { const workload = batches.filter((batch) => batch.trainer_id === row.id && ["confirmed", "in_progress"].includes(batch.status)).reduce((count, batch) => count + batch.student_count, 0); return <article className="im-trainer-card" key={row.id}><span className="im-avatar im-avatar-large">{shortName(row.name)}</span><div><h3>{row.name}</h3><p>{row.expertise || "Specialization not listed"}</p><small>{row.email || "No email"} · {row.phone || "No contact number"}</small></div><footer>{onAvailability ? <select aria-label={`Availability for ${row.name}`} value={row.availability || "available"} onChange={(event) => onAvailability(row.id, event.target.value)}><option value="available">Available</option><option value="busy">Busy</option><option value="unavailable">Unavailable</option></select> : <span className={`im-pill im-pill-${row.availability || "available"}`}>{row.availability || "available"}</span>}<span>{row.experience_years ?? "—"} years</span><strong>{workload} active students</strong></footer></article>; })}{!rows.length && <div className="im-empty im-panel">No trainers have been added yet.</div>}</div></>;
}

function SessionsSection({ rows, batches, onCreate, onUpdate }) {
  return <div className="im-panel"><header><div><h3>Training calendar</h3><small>Session schedule, trainer, meeting links and completion.</small></div>{onCreate && <button className="primary-button" onClick={onCreate}>+ Schedule session</button>}</header><div className="im-session-list">{rows.map((row) => <article key={row.id}><span className="im-session-date"><strong>{new Date(row.starts_at).getDate()}</strong><small>{new Date(row.starts_at).toLocaleString(undefined, { month: "short" })}</small></span><div className="im-session-info"><h4>{row.session_number}. {row.title}</h4><p>{row.topic || row.description || "No session description"}</p><small>{batches.find((batch) => batch.id === row.batch_id)?.name || `Batch #${row.batch_id}`} · {dateText(row.starts_at, true)} · Trainer #{row.trainer_id || "—"}</small>{row.meeting_url && <a href={row.meeting_url} target="_blank" rel="noreferrer">Open meeting link</a>}</div><span className={`im-pill im-pill-${row.status}`}>{row.status}</span>{onUpdate && row.status === "scheduled" && <button className="soft-button compact" onClick={() => onUpdate(row, "completed")}>Mark completed</button>}</article>)}{!rows.length && <div className="im-empty">No training sessions scheduled.</div>}</div></div>;
}

function AttendanceSection({ sessions, batches, selected, setSelected, canMark, onMark }) {
  const session = sessions.find((row) => String(row.id) === String(selected));
  const batch = batches.find((row) => row.id === session?.batch_id);
  return <div className="im-panel"><header><div><h3>Session attendance</h3><small>Present, absent, late and excused records update student progress automatically.</small></div><select value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Choose a session…</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.title} · {dateText(row.starts_at)}</option>)}</select></header>
    {session ? <div className="im-table-wrap"><table className="im-table"><thead><tr><th>Student</th><th>Payment</th><th>Attendance status</th></tr></thead><tbody>{(batch?.students || []).map(({ student }) => <tr key={student.id}><td>{student.full_name}</td><td>{student.payment_status}</td><td>{canMark ? <div className="im-actions">{["present", "absent", "late", "excused"].map((status) => <button key={status} className="soft-button compact" onClick={() => onMark(session, student, status)}>{status}</button>)}</div> : "View only"}</td></tr>)}{!batch?.students?.length && <tr><td colSpan="3"><div className="im-empty">No active students are enrolled in this batch.</div></td></tr>}</tbody></table></div> : <div className="im-empty">Select a scheduled session to take attendance.</div>}
  </div>;
}

function AssignmentsSection({ rows, batches, students, onCreate, onSubmissions, onSubmit }) {
  return <><div className="im-panel im-section-toolbar"><div><h3>Batch assignments</h3><p>Publish practical work, collect submissions and review marks.</p></div>{onCreate && <button className="primary-button" onClick={onCreate}>+ Create assignment</button>}</div><div className="im-assignment-grid">{rows.map((row) => <article key={row.id} className="im-assignment-card"><span className="im-icon-box"><FileText size={18} /></span><div><h3>{row.title}</h3><p>{row.description || "No assignment instructions"}</p><small>{batches.find((batch) => batch.id === row.batch_id)?.name || `Batch #${row.batch_id}`} · Due {dateText(row.due_at, true)} · Max {row.max_score}</small></div><footer>{onSubmissions && <button className="soft-button compact" onClick={() => onSubmissions(row)}>Review submissions</button>}{onSubmit && <button className="soft-button compact" onClick={() => onSubmit(row, row.batch_id)}>Record submission</button>}</footer></article>)}{!rows.length && <div className="im-empty im-panel">No assignments published yet.</div>}</div></>;
}

function ProgressSection({ rows, selected, selectedId, onSelect, setSelectedId }) {
  return <div className="im-progress-layout"><aside className="im-panel"><header><h3>Students</h3></header><div className="im-progress-students">{rows.map((row) => <button key={row.id} className={String(selectedId) === String(row.id) ? "active" : ""} onClick={() => onSelect(row.id)}><span className="im-avatar">{shortName(row.full_name)}</span><span>{row.full_name}<small>{row.selected_domain || "Internship"}</small></span><ChevronDown size={14} /></button>)}</div></aside>
    <section className="im-panel im-progress-panel">{selected ? <><header><div><h3>{selected.student.full_name}</h3><small>{selected.student.selected_domain || "Internship"} · Internship progress</small></div><span className="im-progress-ring">{selected.overall_progress}%</span></header><div className="im-progress-bar"><i style={{ width: `${selected.overall_progress}%` }} /></div><div className="im-progress-metrics"><Metric label="Training sessions" value={`${selected.completed_sessions} / ${selected.total_sessions}`} /><Metric label="Attendance" value={`${selected.attendance_percentage}%`} /><Metric label="Assignments done" value={`${selected.assignments_completed} / ${selected.assignments_assigned}`} /><Metric label="Average score" value={selected.average_assignment_score ?? "—"} /><Metric label="Remaining sessions" value={selected.remaining_sessions} /><Metric label="Pending work" value={selected.pending_assignments} /></div></> : <div className="im-empty">Choose a student to review attendance, assignments and overall progress.</div>}</section></div>;
}

function EvaluationsSection({ rows, batches, manager, onSubmit, onApprove, onCertificate }) {
  return <><div className="im-panel im-section-toolbar"><div><h3>Final internship reviews</h3><p>Weighted criteria are calculated from current settings; management approves the final outcome.</p></div></div>
    <div className="im-batch-grid">{batches.filter((batch) => ["in_progress", "completed"].includes(batch.status)).map((batch) => <article className="im-batch-card" key={batch.id}><header><div><span className="im-eyebrow">{batch.domain}</span><h3>{batch.name}</h3></div><span className={`im-pill im-pill-${batch.status}`}>{batch.status}</span></header><div className="im-eval-roster">{batch.students.map(({ student }) => { const row = rows.find((item) => item.batch_id === batch.id && item.application_id === student.id); return <div key={student.id}><span>{student.full_name}</span>{row ? <><strong>{row.performance_score}%</strong><em className={`im-pill im-pill-${row.result}`}>{row.result.replaceAll("_", " ")}</em>{manager && !row.approved_at && <button className="soft-button compact" onClick={() => onApprove(row, true)}>Approve</button>}{manager && !row.approved_at && <button className="soft-button compact danger" onClick={() => onApprove(row, false)}>Return</button>}{manager && row.approved_at && row.result === "passed" && <button className="soft-button compact" onClick={() => onCertificate(row)}>Issue certificate</button>}</> : onSubmit && <button className="soft-button compact" onClick={() => onSubmit(batch)}>Submit final evaluation</button>}</div>; })}{!batch.students?.length && <small>No active roster.</small>}</div></article>)}{!batches.length && <div className="im-empty im-panel">No active or completed internship batches.</div>}</div>
    <div className="im-panel"><header><h3>Evaluation history</h3></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Student</th><th>Batch</th><th>Weighted score</th><th>Result</th><th>Approval</th><th>Trainer feedback</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>Student #{row.application_id}</td><td>{batches.find((batch) => batch.id === row.batch_id)?.name || `Batch #${row.batch_id}`}</td><td>{row.performance_score}%</td><td><span className={`im-pill im-pill-${row.result}`}>{row.result.replaceAll("_", " ")}</span></td><td>{row.approved_at ? `Approved ${dateText(row.approved_at)}` : "Pending approval"}</td><td>{row.trainer_feedback || "—"}</td></tr>)}{!rows.length && <tr><td colSpan="6"><div className="im-empty">No evaluations have been submitted.</div></td></tr>}</tbody></table></div></div>
  </>;
}

function EvaluationDialog({ form, setForm, batches, config, students, busy, onClose, onSave }) {
  const batch = batches.find((row) => row.id === Number(form.batchId));
  const criteria = Object.keys(config?.evaluation_weights || {});
  return <div className="im-overlay"><section className="im-dialog" role="dialog" aria-modal="true" aria-label="Submit final evaluation"><header><div><span className="im-eyebrow">FINAL REVIEW</span><h2>Submit final evaluation</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></header><div className="im-form-grid"><label className="im-wide"><span>Student</span><select value={form.studentId} onChange={(event) => setForm((current) => ({ ...current, studentId: event.target.value }))}><option value="">Select student…</option>{(batch?.students || []).map(({ student }) => <option key={student.id} value={student.id}>{student.full_name}</option>)}</select></label>{criteria.map((key) => <label key={key}><span>{key.replaceAll("_", " ")} · weight {config.evaluation_weights[key]}%</span><input type="number" min="0" max="100" value={form.criterionScores[key] ?? ""} onChange={(event) => setForm((current) => ({ ...current, criterionScores: { ...current.criterionScores, [key]: event.target.value } }))} /></label>)}<label className="im-wide"><span>Trainer feedback</span><textarea rows="3" value={form.feedback} onChange={(event) => setForm((current) => ({ ...current, feedback: event.target.value }))} /></label><label className="im-wide"><span>Final project details</span><textarea rows="3" value={form.project} onChange={(event) => setForm((current) => ({ ...current, project: event.target.value }))} /></label><label><span>Completion date</span><input type="date" value={form.completionDate} onChange={(event) => setForm((current) => ({ ...current, completionDate: event.target.value }))} /></label></div><footer><button className="soft-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy || !form.studentId || criteria.some((key) => form.criterionScores[key] === "") } onClick={onSave}>{busy ? "Saving…" : "Submit for approval"}</button></footer></section></div>;
}

function CertificatesSection({ rows, students, onPrint }) {
  return <div className="im-panel"><header><div><h3>Completion certificates</h3><small>Generated only for completed batches with an approved passing evaluation.</small></div></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Certificate ID</th><th>Student</th><th>Type</th><th>Issued</th><th>Status</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><strong>{row.certificate_number || `#${row.id}`}</strong></td><td>{students.find((student) => student.id === row.application_id)?.full_name || `Student #${row.application_id}`}</td><td>{row.certificate_type}</td><td>{dateText(row.issued_at)}</td><td><span className={`im-pill im-pill-${row.status}`}>{row.status}</span></td><td>{row.status === "issued" && <button className="soft-button compact" onClick={() => onPrint(row)}>Print / save as PDF</button>}</td></tr>)}{!rows.length && <tr><td colSpan="6"><div className="im-empty">No certificates have been issued.</div></td></tr>}</tbody></table></div><div className="im-note">Certificate verification: use the unique certificate ID with the CRM certificate verification endpoint.</div></div>;
}

function ReportsSection({ overview, reports, batches, syncRuns, onExport }) {
  return <><div className="im-metrics"><Metric label="Registrations" value={overview?.total_registrations} /><Metric label="Eligible students" value={overview?.eligible_students} /><Metric label="Confirmed batches" value={overview?.confirmed_batches} /><Metric label="Completion rate" value={`${reports?.completion?.rate ?? 0}%`} /><Metric label="Student satisfaction" value={reports?.feedback_summary?.average_rating ? `${reports.feedback_summary.average_rating}/5` : "—"} note={`${reports?.feedback_summary?.responses || 0} responses`} /><Metric label="Placement interest" value={reports?.feedback_summary?.placement_interest || 0} note="Student responses" /></div>
    <div className="im-panel"><header><div><h3>Batch performance</h3><small>Roster, outcome and trainer details from live internship records.</small></div><button className="soft-button" onClick={onExport}><Download size={15} />Download student CSV for Excel</button></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Batch</th><th>Domain</th><th>Roster</th><th>Capacity</th><th>Status</th><th>Trainer</th></tr></thead><tbody>{batches.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.domain}</td><td>{row.student_count}</td><td>{row.capacity}</td><td>{row.status}</td><td>{row.trainer_name || "Unassigned"}</td></tr>)}{!batches.length && <tr><td colSpan="6"><div className="im-empty">No batch records.</div></td></tr>}</tbody></table></div></div>
    <div className="im-overview-grid"><ChartBars title="Domain-wise students" rows={reports?.domain_performance || []} labelKey="domain" valueKey="students" /><ChartBars title="Trainer workload" rows={reports?.trainer_performance || []} labelKey="trainer_name" valueKey="active_students" /></div>
    <div className="im-panel"><header><div><h3>Completion outcomes</h3><small>Batch evaluation and trainer performance from recorded evaluations.</small></div></header><div className="im-table-wrap"><table className="im-table"><thead><tr><th>Batch</th><th>Evaluations</th><th>Passed</th><th>Average score</th><th>Pass rate</th></tr></thead><tbody>{(reports?.batch_performance || []).map((row) => <tr key={row.batch_id}><td>{row.batch_name}</td><td>{row.evaluation_count}</td><td>{row.passed}</td><td>{row.average_score === null ? "—" : `${row.average_score}%`}</td><td>{row.evaluation_count ? `${Math.round(row.passed * 100 / row.evaluation_count)}%` : "—"}</td></tr>)}{!reports?.batch_performance?.length && <tr><td colSpan="5"><div className="im-empty">No evaluation data is available yet.</div></td></tr>}</tbody></table></div></div>
    <div className="im-panel"><header><div><h3>Google Form synchronization</h3><small>Manual sync history and retry status.</small></div></header>{syncRuns.length ? <div className="im-sync-list">{syncRuns.map((row) => <div key={row.id}><strong>{row.source}</strong><span>{dateText(row.started_at, true)}</span><span className={`im-pill im-pill-${row.status}`}>{row.status}</span><span>{row.imported_count} added · {row.duplicate_count} matched</span><small>{row.error_message || ""}</small></div>)}</div> : <div className="im-empty">No Google Form sync has been run yet.</div>}</div>
  </>;
}

function SettingsSection({ config, manager, onSave }) {
  if (!config) return <div className="im-panel im-empty">Settings are loading…</div>;
  return <form className="im-panel im-settings" onSubmit={onSave}><header><div><h3>Lifecycle and evaluation policy</h3><small>These values affect certificate eligibility and unpaid batch approvals.</small></div>{manager && <button className="primary-button">Save settings</button>}</header>
    <div className="im-form-grid"><label><span>Minimum attendance for certificate (%)</span><input name="attendance_threshold" type="number" min="0" max="100" defaultValue={config.attendance_threshold} disabled={!manager} /></label><label><span>Passing score (%)</span><input name="passing_score" type="number" min="0" max="100" defaultValue={config.passing_score} disabled={!manager} /></label><label><span>Unpaid students require batch approval</span><select name="unpaid_batch_approval_required" defaultValue={String(config.unpaid_batch_approval_required)} disabled={!manager}><option value="true">Yes</option><option value="false">No</option></select></label></div>
    <h3>Final evaluation weights</h3><div className="im-weight-grid">{Object.entries(config.evaluation_weights || {}).map(([key, value]) => <label key={key}><span>{key.replaceAll("_", " ")}</span><input name={`weight-${key}`} type="number" min="0" max="100" defaultValue={value} disabled={!manager} /></label>)}</div><p className="im-note">Evaluation weights must total 100%. Criteria are calculated as a weighted score.</p></form>;
}

function StudentProfile({ profile, progress, users, manager, coordinator, trainerRole, currentUserId, onClose, onUpdate, onForm, onUpload }) {
  const student = profile.student;
  return <div className="im-overlay"><section className="im-profile-dialog" role="dialog" aria-modal="true" aria-label={`${student.full_name} profile`}><header><div><span className="im-eyebrow">STUDENT PROFILE · #{student.id}</span><h2>{student.full_name}</h2><p>{student.email} · {student.phone || "No mobile number"}</p></div><button className="icon-button" onClick={onClose} aria-label="Close profile"><X size={18} /></button></header>
    <div className="im-profile-status"><label><span>Student status</span><select disabled={!coordinator} value={student.student_status} onChange={(event) => onUpdate(student.id, { student_status: event.target.value })}>{STUDENT_STATUSES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label><span>Assigned employee</span>{manager ? <select value={student.coordinator_id || ""} onChange={(event) => onUpdate(student.id, { coordinator_id: event.target.value ? Number(event.target.value) : null })}><option value="">Unassigned</option>{users.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select> : student.coordinator_id ? <strong>{users.find((person) => person.id === student.coordinator_id)?.full_name || `Employee #${student.coordinator_id}`}</strong> : coordinator ? <button className="soft-button compact" onClick={() => onUpdate(student.id, { coordinator_id: currentUserId })}>Assign to me</button> : <strong>Unassigned</strong>}</label><div><span>Payment status</span><em className={`im-pill im-pill-${student.payment_status}`}>{student.payment_status}</em>{coordinator && <button className="soft-button compact" onClick={() => onForm("payment", { studentId: student.id })}>+ Record payment</button>}</div></div>
    <div className="im-profile-scroll"><div className="im-profile-cards"><article><h3>Registration & academics</h3><dl>{[["College", student.college_name], ["University", student.university], ["Degree", student.degree], ["Department", student.department], ["Academic year", student.current_academic_year], ["Graduation year", student.graduation_year], ["Domain", student.selected_domain], ["Duration", student.preferred_duration_weeks ? `${student.preferred_duration_weeks} weeks` : null], ["Training mode", student.preferred_mode], ["Registered", dateText(student.applied_at)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl></article>
      <article><h3>Student details</h3><dl>{[["Date of birth", dateText(student.date_of_birth)], ["WhatsApp", student.whatsapp_number], ["Technical skills", student.technical_skills], ["Previous experience", student.previous_experience]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl></article>
      <article><h3>Payment details</h3><dl>{[["Option", student.payment_option], ["Amount", money(student.payment_amount)], ["Payment status", student.payment_status], ["Transaction ID", student.payment_transaction_id], ["Source", student.registration_source], ["Form response ID", student.google_form_response_id], ["Sync status", student.sync_status]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl></article>
      <article className="im-wide-card"><h3>Progress snapshot</h3>{progress ? <div className="im-profile-progress"><strong>{progress.overall_progress}%</strong><span>overall</span><span>{progress.attendance_percentage}% attendance</span><span>{progress.completed_sessions}/{progress.total_sessions} sessions</span><span>{progress.assignments_completed}/{progress.assignments_assigned} assignments</span></div> : <p>Progress data is unavailable.</p>}</article>
      <article><header><h3>Follow-up history</h3>{coordinator && <button className="soft-button compact" onClick={() => onForm("followup", { studentId: student.id })}>+ Log call</button>}</header>{profile.followups.length ? profile.followups.map((row) => <div className="im-timeline-row" key={row.id}><i /><div><strong>{row.outcome || "Contact logged"}</strong><p>{row.notes}</p><small>{dateText(row.follow_up_at, true)}{row.next_follow_up_at ? ` · Next: ${dateText(row.next_follow_up_at, true)}` : ""}</small></div></div>) : <p className="im-empty-inline">No follow-up notes yet.</p>}</article>
      <article><h3>Status history</h3>{profile.status_history.length ? profile.status_history.map((row) => <div className="im-history-row" key={row.id}><span>{labelFor(STUDENT_STATUSES, row.from_status)} <b>→</b> {labelFor(STUDENT_STATUSES, row.to_status)}</span><small>{dateText(row.changed_at, true)} {row.note ? `· ${row.note}` : ""}</small></div>) : <p className="im-empty-inline">No status changes yet.</p>}</article>
      <article><header><div><h3>Internship feedback</h3><small>Student satisfaction and trainer feedback</small></div>{trainerRole && <button className="soft-button compact" onClick={() => onForm("feedback", { studentId: student.id })}>+ Add feedback</button>}</header>{profile.feedback?.length ? profile.feedback.map((row) => <div className="im-history-row" key={row.id}><span><strong>{row.feedback_type === "trainer" ? "Trainer" : "Student"} feedback</strong> · {row.rating}/5{row.placement_interest === null || row.placement_interest === undefined ? "" : ` · Placement interest: ${row.placement_interest ? "yes" : "no"}`}</span><small>{row.comments || "No written comments"} · {dateText(row.created_at, true)}</small></div>) : <p className="im-empty-inline">No feedback recorded yet.</p>}</article>
      <article className="im-wide-card"><header><div><h3>Registration documents</h3><small>Private file storage; only authorized CRM roles can open documents.</small></div></header><form className="im-upload-form" onSubmit={onUpload}><input name="document" type="file" accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg" required /><button className="soft-button compact">Upload file</button></form>{profile.documents.length ? <div className="im-doc-list">{profile.documents.map((doc) => <a key={doc.id} href={`${API_BASE}/documents/${doc.id}/download`} onClick={(event) => { event.preventDefault(); fetch(`${API_BASE}/documents/${doc.id}/download`, { headers: { Authorization: `Bearer ${localStorage.getItem("onecrm_token") || ""}` } }).then((response) => response.blob()).then((blob) => { const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = doc.file_name; link.click(); URL.revokeObjectURL(url); }); }}>{doc.file_name} · {dateText(doc.created_at)}</a>)}</div> : <p className="im-empty-inline">No files uploaded.</p>}</article>
      {student.internal_remarks && <article className="im-wide-card"><h3>Internal remarks</h3><p>{student.internal_remarks}</p></article>}
    </div></div><footer className="im-profile-footer"><span>Lead record #{student.lead_id || "—"} · Form sync: {student.sync_status}</span><button className="soft-button" onClick={onClose}>Close profile</button></footer>
  </section></div>;
}

function SubmissionsDialog({ assignment, rows, students, onClose, onReview }) {
  return <div className="im-overlay"><section className="im-dialog" role="dialog" aria-modal="true" aria-label="Review assignment submissions"><header><div><span className="im-eyebrow">ASSIGNMENT REVIEW</span><h2>{assignment.title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></header><div className="im-submission-list">{rows.map((row) => <article key={row.id}><div><strong>{students.find((student) => student.id === row.application_id)?.full_name || `Student #${row.application_id}`}</strong><span className={`im-pill im-pill-${row.status}`}>{row.status.replaceAll("_", " ")}</span><small>Submitted {dateText(row.submitted_at, true)}</small>{row.submission_link && <a href={row.submission_link} target="_blank" rel="noreferrer">Open submission</a>}{row.submission_text && <p>{row.submission_text}</p>}{row.feedback && <small>Feedback: {row.feedback}</small>}</div>{!["evaluated"].includes(row.status) && <div className="im-actions"><button className="soft-button compact" onClick={() => onReview(row, "evaluated")}>Evaluate</button><button className="soft-button compact danger" onClick={() => onReview(row, "rejected_resubmission")}>Request resubmission</button></div>}</article>)}{!rows.length && <div className="im-empty">No student submissions yet.</div>}</div><footer><button className="soft-button" onClick={onClose}>Close</button></footer></section></div>;
}

export default InternshipManagement;
