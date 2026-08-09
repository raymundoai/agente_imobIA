export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  tenant_slug?: string | null;
};

export type DashboardStats = {
  conversations: number;
  leads: number;
  handoffs: number;
  properties: number;
};

export type Conversation = {
  id: string;
  contact_id: string | null;
  phone: string;
  customer_name: string | null;
  status: string;
  mode: string;
  last_message_at: string;
  current_intent?: string | null;
  current_agent?: string;
  channel?: "whatsapp" | "telegram";
  is_group: boolean;
  group_name: string | null;
  last_message_text: string | null;
  last_message_attachments: Message["attachments"];
  last_message_direction: string | null;
};

export type TelegramConnection = {
  configured: boolean;
  status: string;
  bot_id: string | null;
  bot_username: string | null;
  webhook_url: string | null;
  pending_updates: number;
  last_error: string | null;
};

export type Message = {
  id: string;
  direction: string;
  author_type: string;
  text: string;
  created_at: string;
  attachments: Array<{
    type: "image" | "video" | "audio" | "document" | "sticker" | string;
    mimetype?: string;
    fileName?: string;
    fileLength?: number | string;
    url?: string;
    storage_key?: string;
    isAnimated?: boolean;
  }>;
  external_message_id?: string | null;
  sender_external_id?: string | null;
  sender_name?: string | null;
};

export type ConversationDetail = Conversation & { messages: Message[] };

export type ContactKind = "lead" | "tenant" | "owner" | "client";

export type Contact = {
  id: string;
  tenant_id: string;
  name: string;
  phone: string;
  email: string | null;
  kind: ContactKind;
  status: "active" | "inactive";
  tags: string[];
  interest: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type LeadDemand = {
  id: string;
  tenant_id: string;
  contact_id: string | null;
  conversation_id: string | null;
  lead_name: string;
  phone: string;
  purpose: string | null;
  city: string | null;
  property_type: string | null;
  neighborhoods: string[];
  price_min: string | null;
  price_max: string | null;
  bedrooms: number | null;
  parking_spaces: number | null;
  min_area: number | null;
  notes: string | null;
  status: "open" | "qualified" | "in_progress" | "closed";
  crm_contact_id: string | null;
  crm_deal_id: string | null;
};

export type CaptureMission = {
  demand: Pick<LeadDemand, "id" | "lead_name" | "phone" | "purpose" | "property_type" | "city" | "neighborhoods" | "price_min" | "price_max" | "bedrooms" | "parking_spaces">;
  search_filters: Record<string, string | number | string[] | null>;
  existing_matches: Array<{
    id: string;
    title: string;
    source_url: string | null;
    price: string | null;
    score: number;
    matched: string[];
    tradeoffs: string[];
  }>;
  portal_searches: Array<{
    id: string;
    name: string;
    url: string;
    applied_filters: string[];
    pending_filters: string[];
    discovery_mode: "manual" | "assisted" | "automatic";
    status_message: string | null;
  }>;
  federated_sources: Array<{
    id: string;
    name: string;
    domain: string;
    coverage: string;
    source_type: "portal" | "network";
    partnership_friendly: boolean;
    search_url: string;
  }>;
};

export type FederatedSearchSource = {
  source_id: string;
  source_name: string;
  status: "queued" | "running" | "completed" | "failed" | "blocked";
  discovered_count: number;
  imported_count: number;
  error_code: string | null;
  error: string | null;
  parser_version: string | null;
};

export type ExternalPropertyResult = {
  id: string;
  source_id: string;
  source_name: string;
  source_listing_id: string;
  canonical_url: string;
  title: string;
  description: string | null;
  purpose: string | null;
  property_type: string | null;
  state: string | null;
  city: string;
  neighborhood: string | null;
  price: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  parking_spaces: number | null;
  area: number | null;
  primary_image_url: string | null;
  advertiser_name: string | null;
  fit_score: number;
  confidence_score: number;
  matched: string[];
  tradeoffs: string[];
  review_status: "new" | "reviewed" | "saved" | "contacted" | "discarded";
  last_seen_at: string;
};

export type FederatedSearchRun = {
  id: string;
  demand_id: string;
  status: "queued" | "running" | "partial" | "completed" | "failed" | "cancelled";
  filters: Record<string, string | number | string[] | null>;
  source_count: number;
  completed_source_count: number;
  result_count: number;
  error: string | null;
  sources: FederatedSearchSource[];
  results: ExternalPropertyResult[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type Property = {
  id: string;
  tenant_id: string;
  source: string;
  title: string;
  city: string;
  neighborhood: string | null;
  price: string | null;
  sale_price?: string | null;
  rent_price?: string | null;
  purpose: string | null;
  property_type: string | null;
  category?: string;
  status?: string;
  listing_code?: string | null;
  description?: string | null;
  bedrooms: number | null;
  suites?: number | null;
  bathrooms?: number | null;
  parking_spaces: number | null;
  area: number | null;
  land_area?: number | null;
  address?: Record<string, unknown>;
  details?: Record<string, unknown>;
  advertiser_name: string | null;
  advertiser_phone: string | null;
  source_url: string | null;
  via_extension: boolean;
};

export type PropertyImage = {
  id: string;
  property_id: string;
  original_name: string;
  status: "uploaded" | "processing" | "ready" | "failed";
  is_primary: boolean;
  sort_order: number;
  original_size: number;
  original_content_type: string;
  media_type: "image" | "video";
  derived_size: number | null;
  original_url: string;
  display_url: string;
  error: string | null;
};

export type KnowledgeDocument = {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  error: string | null;
};

export type UsageSummaryItem = {
  type: string;
  module: string;
  quantity: number;
  estimated_cost: string;
};

export type CreditAccount = {
  tenant_id: string;
  balance_credits: number;
  reserved_credits: number;
  available_credits: number;
  enforcement_mode: "meter_only" | "enforce";
  unlimited_messages: boolean;
  credit_value_usd: string;
  markup_multiplier: string;
};

export type CreditLedgerItem = {
  id: string;
  delta_credits: number;
  balance_after: number;
  kind: string;
  resource: string | null;
  model: string | null;
  provider_cost_usd: string;
  retail_cost_usd: string;
  description: string | null;
  created_at: string;
};

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  status: string;
  settings: TenantSettings;
  created_at: string;
};

export type TenantSettings = {
  profile?: {
    display_name?: string;
    legal_name?: string;
    document_type?: "cpf" | "cnpj";
    document_number?: string;
    channels?: string;
    business_hours?: string | BusinessHours;
    regions?: string;
    voice_tone?: string;
  };
  channels?: Record<string, unknown>;
  agents?: Record<string, unknown>;
  ai_agent?: {
    handoff_policies?: string;
    autonomy_limits?: string;
    fallback_message?: string;
    faq_scope?: string;
  };
  integrations?: {
    evolution?: {
      base_url?: string;
      instance?: string;
      integration?: string;
      webhook_events?: string;
    };
    hubspot?: {
      status?: string;
      pipeline_id?: string;
      qualified_stage_id?: string;
      owner_default?: string;
      owner_handoff?: string;
    };
    openai?: {
      status?: string;
      chat_model?: string;
      embedding_model?: string;
      embedding_dimensions?: string;
    };
  };
  [key: string]: unknown;
};

export type BusinessDaySchedule = {
  enabled: boolean;
  start: string;
  end: string;
  break_enabled: boolean;
  break_start: string;
  break_end: string;
};

export type BusinessHours = {
  timezone: string;
  days: Record<BusinessWeekday, BusinessDaySchedule>;
};

export type BusinessWeekday =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday"
  | "saturday"
  | "sunday";

export type EvolutionWhatsappConnection = {
  instance: string;
  status: string;
  qrcode: string | null;
  pairing_code: string | null;
  connected_phone: string | null;
  connected_name: string | null;
  webhook_configured: boolean;
  webhook_url: string | null;
  webhook_error: string | null;
};

export type IntegrationSetupSummary = {
  provider: string;
  name: string;
  category: string;
  status: "not_configured" | "awaiting_credentials" | "testing" | "connected" | "error";
  required_items: string[];
  target_resources: string[];
  notes: string | null;
};

export type User = {
  id: string;
  tenant_id: string;
  name: string;
  email: string;
  role: "admin" | "gestor" | "corretor" | "atendente";
  status: "active" | "inactive" | "invited";
  is_master: boolean;
  must_change_password: boolean;
  invitation_expires_at: string | null;
  invited_at: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PasswordSetup = {
  user: User;
  token: string;
  expires_at: string;
};

export type UserAudit = {
  id: string;
  actor_user_id: string | null;
  target_user_id: string | null;
  action: string;
  changes: Record<string, unknown>;
  created_at: string;
};
