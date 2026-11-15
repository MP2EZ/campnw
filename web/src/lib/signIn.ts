/** Pages outside App ask it to open the sign-in modal with this event. */
export const SIGN_IN_EVENT = "campable:sign-in";

/** Open the sign-in modal. `entryPoint` is reported with the auth events. */
export function requestSignIn(entryPoint: string): void {
  window.dispatchEvent(new CustomEvent<string>(SIGN_IN_EVENT, { detail: entryPoint }));
}
