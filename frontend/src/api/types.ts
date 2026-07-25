export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type DashboardStats = {
  conversations: number;
  leads: number;
  handoffs: number;
  maintenance_tickets: number;
  properties: number;
};

export type Conversation = {
  id: string;
  phone: string;
  customer_name: string | null;
  status: string;
  mode: string;
  last_message_at: string;
  current_intent?: string | null;
  current_agent?: string;
  channel?: "whatsapp" | "telegram";
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
};

export type ConversationDetail = Conversation & { messages: Message[] };

export type LeadDemand = {
  id: string;
  tenant_id: string;
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
  status: string;
  crm_contact_id: string | null;
  crm_deal_id: string | null;
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
  images: Array<Record<string, unknown>>;
  advertiser_name: string | null;
  advertiser_phone: string | null;
  source_url: string | null;
  via_extension: boolean;
};

export type CaptureMission = {
  demand: Record<string, string | string[] | null>;
  search_filters: Record<string, string | string[] | number | null>;
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
  }>;
};

export type DiscoverMissionResult = {
  portal: string;
  discovered: number;
  imported: number;
  properties: Property[];
};

export type MaintenanceTicket = {
  id: string;
  tenant_id: string;
  conversation_id: string | null;
  customer_name: string;
  phone: string;
  property_reference: string | null;
  issue_type: string;
  description: string;
  urgency: string;
  status: string;
  assigned_user_id: string | null;
  attachments: Array<Record<string, unknown>>;
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
    channels?: string;
    business_hours?: string;
    regions?: string;
    voice_tone?: string;
  };
  channels?: Record<string, unknown>;
  agents?: Record<string, unknown>;
  ai_agent?: {
    handoff_policies?: string;
    autonomy_limits?: string;
    maintenance_rules?: string;
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
    capture?: Record<string, string | undefined>;
  };
  [key: string]: unknown;
};

export type EvolutionWhatsappConnection = {
  instance: string;
  status: string;
  qrcode: string | null;
  pairing_code: string | null;
  connected_phone: string | null;
  connected_name: string | null;
  webhook_configured: boolean;
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
  status: "active" | "inactive";
  created_at: string;
};
