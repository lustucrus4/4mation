import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProfile, type UserProfile } from "../lib/accountApi";
import { useLab211Auth } from "./useLab211Auth";

export const PROFILE_QUERY_KEY = ["profile"];

export function useAccount() {
  const { authenticated, loading: authLoading } = useLab211Auth();
  const queryClient = useQueryClient();

  const query = useQuery<UserProfile>({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: fetchProfile,
    enabled: authenticated,
    staleTime: 30_000,
    retry: false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });

  return {
    authenticated,
    authLoading,
    profile: query.data ?? null,
    loading: authLoading || (authenticated && query.isLoading),
    error: query.error,
    refresh: invalidate,
  };
}
