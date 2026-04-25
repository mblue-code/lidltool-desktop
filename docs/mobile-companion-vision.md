# Mobile Companion Vision

This document describes the desired product shape for a future LidlTool mobile companion that pairs directly with the desktop app.

This is a desktop-side product vision document, not a self-hosted or cloud roadmap.

## Product Position

The phone app should be:
- a private, local-first personal finance companion
- optimized for everyday budgeting and shopping review
- paired to the desktop app when the user wants local sync
- fully useful on its own between sync sessions

The phone app should not be:
- a public SaaS client
- a cloud-first mobile frontend
- a thin remote control for desktop-only workflows
- an always-on sync daemon
- a replacement for the desktop app

## Core Product Promise

The intended promise is:
- your data stays local
- your phone and desktop can pair directly
- both devices remain usable offline
- sync happens intentionally when both apps are open and reachable

The intended promise is not:
- always-on background sync
- internet-hosted account access
- real-time collaborative multi-device editing across arbitrary networks

## Why Mobile Exists

Desktop is still the richer import, admin, analysis, and repair tool.

Mobile exists because users need a daily surface for:
- checking budgets while shopping
- reviewing recent transactions quickly
- adding manual entries immediately
- looking up item and merchant history on the go
- seeing personal and household finance context without opening the desktop app

## What We Would Love Inside The App

### 1. Home and budget awareness

The phone app should open into a useful daily summary, not a generic dashboard clone.

High-value mobile home content:
- current month spending vs budget
- category overspend warnings
- recent transactions
- upcoming bills
- grocery spend snapshot
- merchant quick lookup
- sync status and last sync time

### 2. Fast transaction review

Transaction history should be a first-class mobile workflow.

Important capabilities:
- browse recent transactions fast
- search by merchant, item, or amount
- open transaction detail
- inspect line items and discounts
- edit categories and notes
- mark records for later desktop review

### 3. Manual capture and quick entry

The phone is the best place for immediate capture.

Important capabilities:
- manual expense entry
- cash transaction entry
- bill/reminder entry
- note-to-self finance capture
- photo/receipt capture for later processing

### 4. Shopping companion workflows

This is where mobile can feel differentiated.

Strong candidates:
- shopping-mode category budget view
- recent price memory for common products
- merchant comparison history from local data
- quick grocery lists linked to budget categories
- household-visible shopping notes

### 5. Goals and alerts

The app should help users make small decisions throughout the week.

Useful surfaces:
- budget risk alerts
- goal progress
- upcoming recurring bill reminders
- unusual spend warnings
- sync-needed reminders when local changes diverge for too long

### 6. Household-aware visibility

If shared finance remains part of the product direction, mobile should support:
- personal workspace
- shared household workspace
- clear indication which records are personal vs shared
- lightweight reallocation or tagging during review

This should be simple and visible, not hidden in advanced settings.

## What Should Stay Desktop-First

These workflows belong primarily on desktop because they are heavier, riskier, or more administrative.

- retailer connector setup
- one-off scrape/sync operations
- account/session administration
- user and household administration
- bulk data correction
- advanced reporting and export
- backup and restore
- plugin-pack management
- AI-heavy review workspaces
- complex document/OCR repair

Mobile may expose status or lightweight follow-up actions for some of these, but should not be the primary place to run them.

## What We Should Explicitly Keep Out

These are attractive but dangerous scope expansions for v1 and likely beyond.

- always-on background sync as a core product requirement
- direct exposure of the desktop backend to the public internet
- mandatory cloud relay infrastructure
- browser-based self-hosted parity on the phone
- full connector bootstrap flows on mobile
- plugin authoring or plugin administration on mobile
- a giant “everything desktop has, but smaller” UI
- server-style automation control surfaces

## UX Principles

### 1. Daily, not administrative

The phone app should feel like something the user opens every day.

That means:
- fast load
- small number of top-level sections
- obvious recency and urgency
- low ceremony for common actions

### 1a. Close to desktop design language

The mobile apps should stay close to the established desktop product language.

That means:
- reuse the same product tone and conceptual model
- preserve key finance information hierarchy from desktop where it fits mobile
- keep the same naming for major domains when possible
- align color, typography direction, icon language, and status semantics with desktop
- adapt layouts for native mobile use without inventing a disconnected visual brand

This does not mean:
- copying desktop layouts literally onto the phone
- forcing desktop density onto small screens
- recreating every desktop interaction on mobile

The goal is:
- clearly the same product family
- optimized for native mobile ergonomics

### 2. Local-first and trustworthy

The app should continuously explain its state clearly:
- paired or unpaired
- last successful sync
- local changes pending sync
- personal vs shared scope

The user should never have to guess where their data is.

### 3. Graceful offline behavior

Offline should be normal, not a failure mode.

The app should still allow:
- browsing local records
- creating entries
- editing eligible records
- queueing changes for next sync

### 4. Sync should be understandable

The user model should be:
- pair once
- use both devices independently
- sync when both are open

If conflicts happen, they should be rare and presented in plain language.

## Recommended Initial Information Architecture

A good starting structure would be:
- `Home`
- `Transactions`
- `Budget`
- `Shopping`
- `Goals`
- `Settings`

Possible secondary surfaces:
- `Bills`
- `Household`
- `Capture`

We should avoid too many top-level tabs.

## Sync and Pairing Product Stance

Recommended v1 stance:
- pair by QR code from desktop
- sync only when both apps are open
- allow explicit `Sync now`
- optionally auto-sync while both apps stay open on the same network
- no promise of permanent background sync

This gives the best tradeoff between:
- privacy
- clarity
- iOS/Android platform safety
- implementation cost
- support burden

## Data Priorities For Mobile

If we phase the product, the mobile app should get these domains first:

Phase 1:
- transaction history
- transaction detail
- budget summaries
- manual entries
- local receipt/photo capture
- sync and pairing UI

Phase 2:
- goals
- recurring bills reminders
- shopping lists and shopping-mode budget context
- household workspace visibility

Phase 3:
- more advanced analytics snippets
- richer item-level editing and allocation flows
- optional notifications derived from local synced state

## Success Criteria

The mobile app is successful if a user can say:
- "I can check my budget while shopping."
- "I can enter spending immediately on my phone."
- "I can see my synced shopping history without trusting a cloud."
- "I still use the desktop app for imports, repair, and deeper analysis."

The mobile app is not successful if users say:
- "I still need the desktop app for every small action."
- "I do not understand when sync happens."
- "The app feels like a broken self-hosted client."
- "It is trying to do everything and does none of it cleanly."

## Current Recommendation

Build the mobile app as a strong daily companion, not as desktop parity.

The product should win on:
- privacy
- practical budgeting utility
- shopping context
- simple local sync

It should deliberately give up:
- cloud convenience
- always-on sync
- server-style control surfaces
- feature parity with the old self-hosted phone harnesses

## Current Product Movement

As of 2026-04-25, the native companion direction is represented in code, not only planning.

The current implementation moves the product toward:
- pairing-first onboarding on Android and iOS
- explicit local sync while desktop and phone are both open
- mobile receipt capture queues that upload artifacts to desktop OCR
- desktop-owned normalized transaction and budget read models synced back to phone
- local mobile storage so the phone remains useful between sync sessions

The current implementation intentionally does not add:
- cloud accounts
- a public mobile backend
- always-on desktop sync
- Flutter or React Native
- mobile connector administration
