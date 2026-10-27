export type WorkArrangement = "remote" | "hybrid" | "onsite" | "any";

export type ConnectionStatus =
  | "connected"
  | "not_connected"
  | "unsupported"
  | "needs_user_action"
  | "sleeping"
  | "rate_limited"
  | "failed"
  | "succeeded";

export interface User {
  id: string;
  email: string;
  display_name: string;
  last_login_at: string | null;
  created_at: string;
}

export interface Employment {
  id: string;
  company: string;
  title: string;
  location: string | null;
  start_date: string;
  end_date: string | null;
  is_current: boolean;
  description: string | null;
  achievements: string[];
  sort_order: number;
}

export type EmploymentInput = Omit<Employment, "id">;

export interface CandidateSkill {
  id: string;
  name: string;
  level: "beginner" | "intermediate" | "advanced" | "expert" | null;
  years_experience: number | null;
  is_primary: boolean;
}

export interface Education {
  institution: string;
  degree: string;
  field_of_study?: string | null;
  start_year?: number | null;
  end_year?: number | null;
}

export interface Certification {
  name: string;
  issuer?: string | null;
  year?: number | null;
}

export interface Completeness {
  score: number;
  missing: string[];
}

export interface Profile {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  headline: string | null;
  summary: string | null;
  total_experience_years: number | null;
  preferred_roles: string[];
  preferred_locations: string[];
  work_arrangement: WorkArrangement;
  salary_currency: string;
  salary_min: number | null;
  salary_max: number | null;
  notice_period_days: number | null;
  excluded_companies: string[];
  target_experience_min: number | null;
  target_experience_max: number | null;
  search_keywords: string[];
  refresh_interval_hours: number;
  education: Education[];
  certifications: Certification[];
  links: Record<string, string>;
  employment: Employment[];
  skills: CandidateSkill[];
  completeness: Completeness;
}

export interface Capabilities {
  mode: "mock" | "unverified" | "manual" | "api";
  search_jobs: boolean;
  get_job_details: boolean;
  get_profile: boolean;
  update_profile: boolean;
  prepare_application: boolean;
  submit_application: boolean;
  get_application_status: boolean;
  notes: string;
}

export interface Portal {
  code: string;
  name: string;
  base_url: string | null;
  status: ConnectionStatus;
  capabilities: Capabilities;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface PortalJob {
  external_id: string;
  title: string;
  company: string;
  location: string | null;
  work_arrangement: string | null;
  description: string | null;
  skills: string[];
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  experience_min: number | null;
  experience_max: number | null;
  url: string | null;
  posted_at: string | null;
  is_synthetic: boolean;
}

export interface Overview {
  profile_completeness: Completeness;
  jobs: { real: number; synthetic: number };
  saved_jobs: number;
  applications: Record<string, number>;
  follow_ups_due: number;
  pending_approvals: number;
  unread_notifications: number;
  portals: { code: string; name: string; status: ConnectionStatus }[];
}

export interface AutomationRules {
  enabled: boolean;
  global_pause: boolean;
  min_match_score: number;
  allowed_titles: string[];
  allowed_locations: string[];
  min_salary: number | null;
  company_allowlist: string[];
  company_blocklist: string[];
  max_applications_per_day: number;
  portal_permissions: Record<string, { enabled: boolean; auto_apply: boolean }>;
  preferred_resume_by_role: Record<string, string>;
  score_weights: Record<string, number>;
  updated_at?: string | null;
}

export interface ReadinessCheck {
  name: string;
  status: "ok" | "warn" | "fail" | "info";
  detail: string;
}

export interface ReadinessReport {
  ready: boolean;
  paid_dependencies: string[];
  checks: ReadinessCheck[];
}

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export type Freshness = "new" | "fresh" | "aging" | "stale" | "expired" | "unknown";
export type ComponentStatus = "match" | "partial" | "mismatch" | "unknown";

export interface MatchComponent {
  weight: number;
  score: number;
  status: ComponentStatus;
  detail: string;
}

export interface JobMatch {
  score: number;
  matched_skills: string[];
  missing_skills: string[];
  eligibility: { status: "eligible" | "ineligible" | "unknown"; reasons: string[] };
  components: Record<string, MatchComponent>;
  engine: string;
  is_saved: boolean;
  feedback: "good_match" | "poor_match" | null;
}

export interface JobSummary {
  id: string;
  title: string;
  company: string;
  location: string | null;
  work_arrangement: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  experience_min: number | null;
  experience_max: number | null;
  posted_at: string | null;
  expires_at: string | null;
  last_seen_at: string | null;
  status: string;
  freshness: Freshness;
  is_synthetic: boolean;
  source_count: number;
  match: JobMatch | null;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  skills: string[];
  canonical_url: string | null;
  sources: { portal: string; external_id: string; url: string | null; fetched_at: string }[];
  explanation: string | null;
}

export interface TaskRun {
  id: string;
  kind: string;
  status: "running" | "succeeded" | "failed" | "interrupted";
  trigger: string;
  result: {
    fetched?: number;
    created?: number;
    updated?: number;
    merged?: number;
    expired?: number;
    portals_searched?: string[];
    portals_skipped?: Record<string, string>;
    portal_errors?: Record<string, string>;
  };
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface JobList {
  items: JobSummary[];
  total: number;
  last_refresh: TaskRun | null;
  refresh_due: boolean;
}

export interface ResumeItem {
  id: string;
  label: string;
  kind: "uploaded" | "master" | "tailored";
  version: number;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  target_role: string | null;
  job_id: string | null;
  parent_resume_id: string | null;
  created_at: string;
}

export interface ParsedEmployment {
  heading: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  date_text: string;
}

export interface ResumeSuggestions {
  full_name: string | null;
  headline: string | null;
  email: string | null;
  phone: string | null;
  links: Record<string, string>;
  summary: string | null;
  total_experience_years: number | null;
  skills: string[];
  employment: ParsedEmployment[];
  certifications: string[];
  education_text: string | null;
  sections_found: string[];
}

export interface UploadResult {
  resume: ResumeItem;
  duplicate: boolean;
  suggestions: ResumeSuggestions;
}

export interface DocumentItem {
  id: string;
  kind: "cover_letter" | "screening_answers";
  title: string;
  version: number;
  job_id: string | null;
  sha256: string;
  content: Record<string, unknown>;
  created_at: string;
}

export interface CoverLetterContent {
  greeting: string;
  paragraphs: string[];
  sign_off: string;
}

export interface ScreeningAnswer {
  question: string;
  answer: string | null;
  category: string;
  needs_confirmation: boolean;
  reason: string;
}

export interface ApplicationEvent {
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ApplicationItem {
  id: string;
  job_id: string;
  job_title: string;
  company: string;
  job_is_synthetic: boolean;
  portal: string | null;
  status: string;
  applied_via: "manual" | "simulated" | "portal";
  is_simulated: boolean;
  external_reference: string | null;
  submitted_at: string | null;
  follow_up_at: string | null;
  follow_up_due: boolean;
  resume_id: string | null;
  cover_letter_id: string | null;
  notes: string | null;
  created_at: string;
  allowed_next: string[];
  events: ApplicationEvent[];
}
