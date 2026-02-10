/**
 * Glide Field Mappings - OFFICIAL SCHEMA
 * Source: Glide Tables SDK export (2026-01-14)
 *
 * These cryptic IDs are Glide's internal column identifiers.
 * DO NOT change unless Glide schema changes.
 */

// =============================================================================
// RESTAURANTS TABLE - native-table-ojIjQjDcDAEOpdtZG5Ao
// =============================================================================
export const RESTAURANT_FIELDS = {
  // Core identifiers
  name: 'MHXYO',
  casinoId: '2Ca0T',           // Links to casinos table
  techId: 'g5WAm',             // Links to technicians

  // Oil/Product info
  oilType: 'U0Jf2',            // e.g., "StableMAX - Bulk", "SoyMAX - 35# Jib"
  oilForm: '0RcWz',
  tpmThreshold: 'zPYNY',       // TPM threshold number

  // Status
  status: 's8tNr',             // "Open", etc.
  active: 'lA5EU',
  replacementAgreement: 'g9zbE',

  // Schedule
  scheduleParameters: 'Po4Zg', // "Daily", "Certain Days", etc.
  days: 'lf0gF',               // "Monday,Tuesday,..." comma-separated

  // Contacts
  primaryContactName: 'doeXs',
  primaryContactEmail: 'a3ffP',
  secondaryContactName: 'Ie35Z',  // Often chef name
  secondaryContactEmail: 'maCR5',

  // Assignment/Override
  assignmentString: 'h90Ts',
  assignmentOverrideTechJson: 'Xz5zq',
  assignmentOverrideDay: 'k4SLM',
  assignmentDateToClearTechOverRide: 'uwU2A',
  assignmentIsLongTermAndExcludeFromWf: 'Ny3eQ',

  // Other
  notes: '08Hj9',
  groupIdStamped: 'cDEde',
} as const;

// =============================================================================
// CASINOS TABLE - native-table-Gy2xHsC7urEttrz80hS7
// =============================================================================
export const CASINO_FIELDS = {
  name: 'Name',                // Casinos use readable "Name" (not cryptic ID)
  address: 'L9K9x',
  oilType: 'UYUGq',
  techId: 'ro9f5',
} as const;

// =============================================================================
// FRYERS TABLE - native-table-r2BIqSLhezVbOKGeRJj8
// =============================================================================
export const FRYER_FIELDS = {
  name: 'Name',                // "Fryer 1", "Fryer 2", etc.
  restaurantId: '2uBBn',       // Links to restaurant glide_row_id
  capacity: 'xhrM0',           // Capacity in lbs
} as const;

// =============================================================================
// Backwards-compatible export for existing code
// =============================================================================
export const VEGAS_GLIDE_FIELDS = {
  restaurants: RESTAURANT_FIELDS,
  casinos: CASINO_FIELDS,
  fryers: FRYER_FIELDS,
} as const;

// Required fields for drift detection
export const VEGAS_GLIDE_REQUIRED_FIELDS = {
  restaurants: [
    RESTAURANT_FIELDS.name,
    RESTAURANT_FIELDS.casinoId,
    RESTAURANT_FIELDS.scheduleParameters,
  ],
  casinos: [
    CASINO_FIELDS.name,
  ],
  fryers: [
    FRYER_FIELDS.restaurantId,
  ],
} as const;

// =============================================================================
// Drift Detection Utilities
// =============================================================================

function hasOwnKey(record: unknown, key: string): boolean {
  if (typeof record !== 'object' || record === null) return false;
  return Object.prototype.hasOwnProperty.call(record, key);
}

export function detectGlideFieldDrift(
  rows: ReadonlyArray<Record<string, unknown>>,
  requiredFields: readonly string[]
): string[] {
  return requiredFields.filter(
    (key) => !rows.some((row) => hasOwnKey(row, key))
  );
}

export class GlideSchemaDriftError extends Error {
  readonly entity: string;
  readonly missingFields: string[];

  constructor(params: { entity: string; missingFields: string[]; hint?: string }) {
    const hint = params.hint ? ` Hint: ${params.hint}` : '';
    super(
      `Glide schema drift detected for ${params.entity}: missing fields: ${params.missingFields.join(', ')}.${hint}`
    );
    this.name = 'GlideSchemaDriftError';
    this.entity = params.entity;
    this.missingFields = params.missingFields;
  }
}

export function assertNoGlideFieldDrift(params: {
  entity: string;
  rows: ReadonlyArray<Record<string, unknown>>;
  requiredFields: readonly string[];
  hint?: string;
}): void {
  if (params.rows.length === 0) return;
  const missingFields = detectGlideFieldDrift(params.rows, params.requiredFields);
  if (missingFields.length === 0) return;
  throw new GlideSchemaDriftError({
    entity: params.entity,
    missingFields,
    hint: params.hint,
  });
}

// =============================================================================
// Field name reverse lookup (for debugging)
// =============================================================================
export function getFieldName(glideId: string): string | undefined {
  for (const [tableName, fields] of Object.entries(VEGAS_GLIDE_FIELDS)) {
    for (const [fieldName, id] of Object.entries(fields)) {
      if (id === glideId) return `${tableName}.${fieldName}`;
    }
  }
  return undefined;
}
