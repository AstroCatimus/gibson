/**
 * Canonical condition grade list.
 * Must match the CHECK constraint in db/migrations/001_schema_core.sql:
 *   condition_grade IN ('Fine','Very Good+','Very Good','Good+','Good','Fair','Poor')
 *
 * Single source of truth — import everywhere grades are shown or sent to the API.
 */
export const GRADES = [
  'Fine',
  'Very Good+',
  'Very Good',
  'Good+',
  'Good',
  'Fair',
  'Poor',
];
