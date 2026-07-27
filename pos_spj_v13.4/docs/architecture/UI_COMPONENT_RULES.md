# UI Component Rules

## Purpose

The desktop UI must use standard components so validation, formatting, search, and user experience remain consistent across modules.

## Required components

Use standard components for:

- numeric input
- money input
- quantity input
- percent input
- integer input
- phone input
- entity search selectors
- address input
- product search
- customer search
- supplier search
- employee search
- branch search
- driver search
- asset search
- status badges
- date range filters

## Numeric fields

Numeric capture fields must start at absolute zero or empty. Do not add arbitrary hardcoded defaults such as `1`, `7`, `10`, `30`, `50`, or `100` in UI.

If a functional default is required, it must come from `SystemSettingsService` or `ModuleSettingsService`.

## Entity selection

Where a user selects a product, customer, supplier, employee, recipe, asset, branch, or driver, use search/autocomplete instead of long preloaded lists.

## Phone input

Phone fields must use a standard phone component that supports WhatsApp/E.164 formatting. Do not introduce plain `QLineEdit` phone capture in new UI work.

## Address input

Address capture must use an address component with map/autocomplete support and a manual fallback. The UI must keep Spanish labels and helper text.

## UI data access

UI components must not execute SQL. Components may call QueryServices for reads and use cases for mutations through explicit dependencies.
