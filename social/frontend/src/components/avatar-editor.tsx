"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  accountMessage,
  accountRequest,
  type Account,
} from "@/lib/api/account";
import { Button, PlayerAvatar } from "./ui";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./ui/notchset/dialog";

export function AvatarEditor({ account }: { account: Account }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (preview) return () => URL.revokeObjectURL(preview);
  }, [preview]);
  function close(value: boolean) {
    if (busy) return;
    setOpen(value);
    setFile(null);
    setPreview(null);
    setError(null);
  }
  async function save(remove = false) {
    if (!remove && !file) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await accountRequest<Account>(
        "/me/avatar",
        remove ? "DELETE" : "POST",
        undefined,
        remove ? undefined : file!,
      );
      await client.cancelQueries();
      client.setQueryData(["account"], result);
      // Authorized data is refetched; no avatar state is copied between pages.
      await client.invalidateQueries();
      setOpen(false);
      setFile(null);
      setPreview(null);
      setSaved(true);
    } catch (failure) {
      setError(accountMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="avatar-editor">
      <Dialog open={open} onOpenChange={close}>
        <DialogTrigger
          className="avatar-change-trigger"
          aria-label="Change avatar"
        >
          <PlayerAvatar
            name={account.display_name}
            uploadedSrc={account.avatar_url}
            large
          />
          <span>Change avatar</span>
        </DialogTrigger>
        <DialogContent className="avatar-dialog">
          <DialogTitle>Your SteamScope avatar</DialogTitle>
          <DialogDescription>
            Choose a PNG, JPEG or WebP up to 5 MiB. We crop it to a square. Your
            profile privacy applies; your Steam avatar stays separate.
          </DialogDescription>
          <div className="avatar-preview">
            {file && preview ? (
              <Image
                src={preview}
                alt="Selected avatar preview"
                width={160}
                height={160}
                unoptimized
                onError={() => {
                  setError(
                    "This image cannot be previewed. Choose another image.",
                  );
                  setFile(null);
                  setPreview(null);
                }}
              />
            ) : (
              <PlayerAvatar
                name={account.display_name}
                uploadedSrc={account.avatar_url}
                large
              />
            )}
          </div>
          <label htmlFor="avatar-file">Choose image</label>
          <input
            id="avatar-file"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            disabled={busy}
            onChange={(event) => {
              const selected = event.currentTarget.files?.[0];
              setError(null);
              setFile(null);
              setPreview(null);
              if (!selected) return;
              if (
                !["image/png", "image/jpeg", "image/webp"].includes(
                  selected.type,
                )
              )
                setError("Choose a PNG, JPEG or WebP image.");
              else if (selected.size > 5 * 1024 * 1024)
                setError("Choose an image smaller than 5 MiB.");
              else {
                setFile(selected);
                setPreview(URL.createObjectURL(selected));
              }
              event.currentTarget.value = "";
            }}
          />
          {file && (
            <p role="status">
              Ready to save · {Math.ceil(file.size / 1024)} KiB
            </p>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="avatar-actions">
            <Button disabled={busy || !file} onClick={() => void save()}>
              {busy ? "Saving…" : "Save avatar"}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => close(false)}
            >
              Cancel
            </Button>
            {account.avatar_url && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void save(true)}
              >
                Remove avatar
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
      {saved && (
        <p role="status" className="form-success">
          Avatar saved.
        </p>
      )}
    </div>
  );
}
