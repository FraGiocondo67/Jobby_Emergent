import { useEffect, useState } from "react";
import * as Location from "expo-location";

export const TREVISO = { lat: 45.6669, lng: 12.2433 };

/**
 * Returns the device's real GPS coordinates, falling back to Treviso when
 * permission is denied or GPS is unavailable. Never blocks rendering.
 */
export function useDeviceLocation(fallback = TREVISO) {
  const [coords, setCoords] = useState(fallback);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { status } = await Location.getForegroundPermissionsAsync();
        let granted = status === "granted";
        if (!granted) {
          const req = await Location.requestForegroundPermissionsAsync();
          granted = req.status === "granted";
        }
        if (granted) {
          const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          if (alive) setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
        }
      } catch {
        // keep fallback
      } finally {
        if (alive) setReady(true);
      }
    })();
    return () => { alive = false; };
  }, []);

  return { coords, ready };
}
