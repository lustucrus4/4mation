import { useCallback, useEffect, useState } from "react";
import {
  getLab211Session,
  onLab211SessionChange,
  type Lab211Session,
  type Lab211User,
} from "../lib/lab211";

export function useLab211Auth() {
  const [session, setSession] = useState<Lab211Session>({
    authenticated: false,
    user: null,
  });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const s = await getLab211Session(true);
    setSession(s);
    setLoading(false);
    return s;
  }, []);

  useEffect(() => {
    let active = true;
    let unsubscribe = () => {};

    (async () => {
      const s = await getLab211Session();
      if (active) {
        setSession(s);
        setLoading(false);
      }
      unsubscribe = await onLab211SessionChange((next) => {
        if (active) setSession(next);
      });
    })();

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  return {
    authenticated: session.authenticated,
    user: session.user as Lab211User | null,
    loading,
    refresh,
  };
}
