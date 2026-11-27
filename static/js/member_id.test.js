/* Node regression tests for the real-time identification formatter.
 * Run with: node static/js/member_id.test.js
 */
const assert = require("node:assert/strict");
const api = require("./member_id.js");

const profiles = [
  {
    id_type: "ghana_card", label: "Ghana Card", prefix: "GHA", display: "ghana_card",
    sanitize: "digits", pattern: "[0-9]{10}", min_length: 10, max_length: 10,
    issuing_authority: "National Identification Authority (NIA)",
    error: "Your Ghana Card number must contain exactly 10 digits.",
  },
  {
    id_type: "voter_id", label: "Voter ID", prefix: "", display: "plain",
    sanitize: "digits", pattern: "[0-9]{10}", min_length: 10, max_length: 10,
    error: "Enter a valid 10-digit Voter ID number.",
  },
  {
    id_type: "nhis", label: "NHIS", prefix: "", display: "plain",
    sanitize: "digits", pattern: "[0-9]{8}", min_length: 8, max_length: 8,
    error: "Your NHIS membership number must contain exactly 8 digits.",
  },
  {
    id_type: "passport", label: "Passport", prefix: "", display: "plain",
    sanitize: "upper_alnum", pattern: "[A-Z0-9]{1,20}", min_length: 1, max_length: 20,
    error: "Enter a valid passport number.",
  },
  {
    id_type: "drivers_licence", label: "Driver's Licence", prefix: "", display: "plain",
    sanitize: "upper_alnum", pattern: "[A-Z0-9]{1,20}", min_length: 1, max_length: 20,
    error: "Enter a valid driving licence number.",
  },
  {
    id_type: "other", label: "Other", prefix: "", display: "plain",
    sanitize: "plain", pattern: "", min_length: 1, max_length: 100,
    error: "Enter a valid identification number.",
  },
];

const f = api.formattersFromConfig(profiles);

function insert(value, caret, text) {
  return value.slice(0, caret) + text + value.slice(caret);
}

function backspace(value, caret) {
  return value.slice(0, caret - 1) + value.slice(caret);
}

// Ghana Card: one keystroke at a time, including automatic prefix and hyphens.
let typed = f.ghana_card.toDisplay("");
const digits = "1234567890";
for (let count = 1; count <= 10; count += 1) {
  const expected = "GHA-" + digits.slice(0, Math.min(count, 9)) + (count > 9 ? "-" + digits.slice(9) : "");
  const result = api.applyValue(f.ghana_card, typed + digits[count - 1], (typed + digits[count - 1]).length);
  typed = result.display;
  assert.equal(typed, expected, "Ghana Card keystroke " + count);
  assert.equal(result.data, digits.slice(0, count));
  assert.equal(result.caret, typed.length, "caret after keystroke " + count);
}

// Invalid characters never enter the canonical value and the caret stays put.
let invalid = insert("GHA-123", 5, "x");
let result = api.applyValue(f.ghana_card, invalid, 6);
assert.equal(result.display, "GHA-123");
assert.equal(result.data, "123");
assert.equal(result.caret, 5);

// Backspace in the middle removes the digit, not the generated separators.
result = api.applyValue(f.ghana_card, backspace("GHA-123456789-0", 7), 6);
assert.equal(result.data, "124567890");
assert.equal(result.display, "GHA-124567890");
assert.equal(result.caret, 6);

// Backspace against the prefix cannot delete or shift it.
result = api.applyValue(f.ghana_card, backspace("GHA-123", 4), 3);
assert.equal(result.display, "GHA-123");
assert.equal(result.caret, 4);

// Pasting raw digits, spaced digits or the formatted display gives one result.
for (const pasted of ["1234567890", " 123 456 7890 ", "GHA-123456789-0"]) {
  result = api.applyValue(f.ghana_card, pasted, pasted.length);
  assert.equal(result.display, "GHA-123456789-0");
  assert.equal(result.data, "1234567890");
  assert.equal(result.caret, 15);
}

// Extra pasted digits are capped without losing the first ten.
result = api.applyValue(f.ghana_card, "123456789012", 12);
assert.equal(result.data, "1234567890");
assert.equal(result.display, "GHA-123456789-0");

// Editing an existing raw value displays the generated format.
result = api.applyValue(f.ghana_card, "1234567890", 10);
assert.equal(result.display, "GHA-123456789-0");
assert.equal(result.caret, 15);

// Voter ID and NHIS keep leading zeros and invent nothing.
assert.equal(f.voter_id.toDisplay(f.voter_id.toData("0444901295")), "0444901295");
assert.equal(f.voter_id.toDisplay(f.voter_id.toData("0000000001")), "0000000001");
assert.equal(f.nhis.toDisplay(f.nhis.toData("00123456")), "00123456");
result = api.applyValue(f.nhis, "00a123456", 9);
assert.equal(result.display, "00123456");

// Passport and DVLA values are uppercased, spaces are removed, order is kept.
result = api.applyValue(f.passport, " g1 23! ", 7);
assert.equal(result.data, "G123");
assert.equal(result.display, "G123");
assert.equal(result.caret, 4);
assert.equal(f.drivers_licence.toDisplay(f.drivers_licence.toData(" dl 001234 ")), "DL001234");

// Other keeps the exact document reference.
assert.equal(f.other.toDisplay(f.other.toData("Ref/2026-001")), "Ref/2026-001");

// Switching types carries the canonical value and regenerates the presentation.
const canonical = f.ghana_card.toData("GHA-123456789-0");
assert.equal(f.voter_id.toDisplay(f.voter_id.toData(canonical)), "1234567890");
assert.equal(f.passport.toDisplay(f.passport.toData(canonical)), "1234567890");
assert.equal(
  f.ghana_card.toDisplay(f.ghana_card.toData(f.passport.toData("ab 12"))),
  "GHA-12"
);

// The issuing authority travels with the public profile so the browser can
// fill it as soon as a document type is chosen.
assert.equal(f.ghana_card.issuingAuthority, "National Identification Authority (NIA)");

// Frontend validation mirrors the backend without verifying identity.
assert.equal(f.ghana_card.validate("1234567890"), "");
assert.notEqual(f.ghana_card.validate("123"), "");
assert.equal(f.voter_id.validate("0444901295"), "");
assert.notEqual(f.voter_id.validate("0444901295a"), "");

console.log("member_id.js: all formatter tests passed");
