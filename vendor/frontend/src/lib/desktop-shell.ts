type DesktopControlCenterBridge = {
  openControlCenter?: () => Promise<void>;
};

export function hasDesktopControlCenterBridge(): boolean {
  const desktopApi = (window as unknown as { desktopApi?: DesktopControlCenterBridge }).desktopApi;
  return typeof desktopApi?.openControlCenter === "function";
}

export async function openDesktopControlCenter(): Promise<void> {
  const desktopApi = (window as unknown as { desktopApi?: DesktopControlCenterBridge }).desktopApi;
  if (typeof desktopApi?.openControlCenter !== "function") {
    throw new Error("Desktop control center is not available in this environment.");
  }
  await desktopApi.openControlCenter();
}
