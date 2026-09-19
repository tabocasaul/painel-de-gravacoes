"""Display-only preparation and camera status from validated local records."""


def video_readiness(name, prepared, cropped, phones, installed, background):
    ready = bool(prepared)
    current = background if background.get('name') == name else {}
    state = 'ready' if ready else 'missing'
    if not ready and current.get('busy'):
        state = 'preparing'
    elif not ready and current.get('error'):
        state = 'error'
    preparation = dict(ready=ready, state=state, croppedReady=bool(cropped),
                       progress=current.get('progress', 0) if state == 'preparing' else 0,
                       preparingCropped=state == 'preparing' and bool(current.get('fill')))
    if state == 'error':
        preparation['error'] = str(current['error'])

    # Match the prepared content identity, never just a reused filename.
    assets = {str(meta['sha256']) + ':' + str(fill)
              for meta, fill in ((prepared, False), (cropped, True))
              if meta and meta.get('sha256')}
    serials = {phone['serial'] for phone in phones}
    confirmed = staged = 0
    for serial in serials:
        record = installed.get(serial) or {}
        if not record.get('assetId') or record['assetId'] not in assets:
            continue
        if record.get('confirmed'):
            confirmed += 1
        elif record.get('staged'):
            staged += 1
    total = len(serials)
    cameras = dict(total=total, confirmed=confirmed, staged=staged,
                   allConfirmed=total > 0 and confirmed == total,
                   allAssigned=total > 0 and confirmed + staged == total)
    return dict(preparation=preparation, cameras=cameras)
