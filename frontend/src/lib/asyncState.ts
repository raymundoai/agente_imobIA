export async function runWithLoading<T>(
  setLoading: (loading: boolean) => void,
  work: () => Promise<T>,
  onError: (error: unknown) => void,
): Promise<T | undefined> {
  setLoading(true);
  try {
    return await work();
  } catch (error) {
    onError(error);
    return undefined;
  } finally {
    setLoading(false);
  }
}
