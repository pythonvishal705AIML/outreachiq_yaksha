# UI Flow: Lead Selection & Campaign Creation

## Visual Flow Guide

### Step 1: Apollo Lead Search Results
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Campaign Intelligence Agent                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Found 20 leads                                               │
│ Search: abc-123-def                                          │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 1  John Smith                                         │   │
│ │    CEO                                                │   │
│ │    Acme Corp                                          │   │
│ │    📍 San Francisco, CA                               │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ 2  Jane Doe                                           │   │
│ │    Founder & CEO                                      │   │
│ │    TechStart Inc                                      │   │
│ │    📍 New York, NY                                    │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ 3  Adam Wilson                                        │   │
│ │    Cofounder & CEO                                    │   │
│ │    FinanceHub                                         │   │
│ │    📍 Austin, TX                                      │   │
│ ├──────────────────────────────────────────────────────┤   │
│ │ ... and 17 more leads                                 │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 2: Lead Selection Panel (NEW!)
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Campaign Intelligence Agent                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 🔷 Select leads for your campaign                    │   │
│ │ Choose how many leads to include in this campaign    │   │
│ │                                                       │   │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│   │
│ │ │All leads │ │ Top 75%  │ │ Top 50%  │ │ Top 25%  ││   │
│ │ │20 leads  │ │ 15 leads │ │ 10 leads │ │ 5 leads  ││   │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘│   │
│ │                                                       │   │
│ │ [Hover effect: Blue border + glow]                   │   │
│ │ [Selected: Blue background + checkmark]              │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 3: Selection Confirmation
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Campaign Intelligence Agent                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ✅ Selected 15 leads (75%) — lead list created              │
│                                                              │
│ Great! Now let's build your campaign.                       │
│ What's the goal of this campaign?                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 4: Campaign Summary with Send Options
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Campaign Intelligence Agent                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Campaign Ready                                        │   │
│ │ Fintech CEO Outreach                                  │   │
│ │ [draft] [3 email steps] [ID: abc12345...]            │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ STEP 1  [⚡ Immediate] [📬 Always send]              │   │
│ │                                                       │   │
│ │ From: {{sender_name}}                                 │   │
│ │ To: {{first_name}}                                    │   │
│ │ Subject: Quick question about your fintech growth    │   │
│ │                                                       │   │
│ │ Hi {{first_name}},                                    │   │
│ │                                                       │   │
│ │ I noticed your work at {{company}} and wanted to     │   │
│ │ reach out about...                                    │   │
│ │                                                       │   │
│ │ ┌──────────────┐  ┌──────────────────────┐          │   │
│ │ │ 📧 Send Test │  │ 🚀 Send to All Leads │          │   │
│ │ └──────────────┘  └──────────────────────┘          │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ STEP 2  [⏱ 3d delay] [🔁 If not replied]            │   │
│ │ ...                                                   │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 5: Send Confirmation
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Campaign Intelligence Agent                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ℹ️ Sending from: john@company.com                           │
│                                                              │
│ ✅ Campaign emails sent from john@company.com!              │
│ Sent: 15 / 15 leads                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## UI Components Breakdown

### 1. Lead Results Card
- **Background**: Dark navy with subtle border
- **Layout**: Numbered list with lead details
- **Info displayed**: Name, title, company, location
- **Truncation**: Shows top 5, then "... and X more"

### 2. Lead Selection Panel
- **Background**: Slightly lighter navy with border
- **Title**: Icon + "Select leads for your campaign"
- **Subtitle**: Helper text explaining the action
- **Buttons**: 4-column grid layout
  - Default: Dark background, light border
  - Hover: Blue border + glow effect
  - Selected: Blue background + blue text
  - Disabled: Reduced opacity

### 3. Selection Button
```
┌──────────┐
│ All leads│  ← Label (bold, 12px)
│ 20 leads │  ← Count (lighter, 11px)
└──────────┘
```

### 4. Campaign Summary Card
- **Hero section**: Campaign name, status badges
- **Email steps**: Expandable cards with preview
- **Action buttons**: Test send + Send to all
- **Styling**: Gradient backgrounds, subtle shadows

## Color Scheme

```css
/* Lead Selection Panel */
--panel-bg: var(--navy-3)        /* #1a2332 */
--panel-border: var(--border-m)  /* rgba(255,255,255,0.08) */

/* Selection Buttons */
--btn-bg: var(--navy-4)          /* #0f1419 */
--btn-border: var(--border)      /* rgba(255,255,255,0.06) */
--btn-hover-border: var(--blue-light)  /* #60a5fa */
--btn-hover-bg: var(--blue-soft)       /* rgba(59,130,246,0.1) */
--btn-selected-bg: var(--blue-glow)    /* rgba(59,130,246,0.15) */
--btn-selected-border: var(--blue)     /* #3b82f6 */

/* Text */
--title-color: var(--white-90)   /* rgba(255,255,255,0.9) */
--subtitle-color: var(--slate)   /* #94a3b8 */
--count-color: var(--slate)      /* #94a3b8 */
```

## Responsive Behavior

### Desktop (> 1024px)
- 4-column grid for selection buttons
- Full campaign summary with all details
- Side-by-side action buttons

### Tablet (768px - 1024px)
- 2-column grid for selection buttons
- Stacked campaign cards
- Full-width action buttons

### Mobile (< 768px)
- 1-column grid for selection buttons
- Simplified lead cards
- Stacked action buttons

## Interaction States

### Lead Selection Button States
1. **Default**: Dark background, subtle border
2. **Hover**: Blue border glow, lighter background
3. **Active/Pressed**: Slightly darker, border pulse
4. **Selected**: Blue background, blue text, checkmark
5. **Disabled**: 50% opacity, no pointer events
6. **Loading**: "Selecting..." text, spinner icon

### Send Button States
1. **Default**: Gradient background, white text
2. **Hover**: Brighter gradient, slight scale
3. **Active**: Pressed effect, darker gradient
4. **Disabled**: Gray background, reduced opacity
5. **Loading**: "Sending..." text, spinner

## Accessibility

### Keyboard Navigation
- Tab through selection buttons
- Enter/Space to select
- Escape to cancel modal
- Arrow keys for button navigation

### Screen Reader Support
- ARIA labels for all buttons
- Role="button" for clickable elements
- Live regions for status updates
- Alt text for icons

### Focus Indicators
- Visible focus ring (blue, 2px)
- High contrast mode support
- Skip to content links

## Animation Timing

```css
/* Smooth transitions */
transition: all 0.15s ease-in-out;

/* Button hover */
transition: border-color 0.15s, background 0.15s;

/* Panel slide-in */
animation: slideUp 0.3s ease-out;

/* Success message */
animation: fadeIn 0.4s ease-in;
```

## Testing Checklist

- [ ] Lead results display correctly
- [ ] Selection panel appears after results
- [ ] All 4 percentage options work
- [ ] Selected button shows blue highlight
- [ ] Confirmation message appears
- [ ] Campaign summary displays
- [ ] Send buttons are functional
- [ ] Error messages display properly
- [ ] Responsive on mobile/tablet
- [ ] Keyboard navigation works
- [ ] Screen reader announces changes
