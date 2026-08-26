/**
 * The two DOM ids that tie a tab to its panel.
 *
 * They live together because they are one contract: `aria-controls` on the tab
 * must name the same element `aria-labelledby` on the panel points back at, and
 * the tab strip and the panel are rendered by different files. A prefix changed
 * in one of them and not the other breaks the association silently — nothing on
 * screen moves.
 */

export function tabButtonId(tab: string): string {
  return `tab-${tab}`;
}

export function tabPanelId(tab: string): string {
  return `tabpanel-${tab}`;
}
