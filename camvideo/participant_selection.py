"""Validate recording choices before preparing or recovering any phone."""


def validate_simultaneous(value):
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError('Informe uma quantidade simultânea inteira maior que zero.')
    return value


def recording_options(options):
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError('Opções de gravação inválidas.')
    result = dict(options)
    result['simultaneous'] = validate_simultaneous(result.get('simultaneous'))
    scope = result.get('scope', 'all')
    if scope not in ('all', 'online', 'selected'):
        raise ValueError('Escolha os celulares participantes.')
    result['scope'] = scope
    if scope == 'selected':
        serials = result.get('selectedSerials')
        if not isinstance(serials, list) or not serials:
            raise ValueError('Escolha pelo menos um celular participante.')
        if any(not isinstance(serial, str) or not serial.strip() for serial in serials):
            raise ValueError('Lista de celulares participantes inválida.')
        if len(set(serials)) != len(serials):
            raise ValueError('Não repita um celular na lista de participantes.')
        result['selectedSerials'] = list(serials)
    return result


def select_participants(targets, options, status):
    """Return a subset keyed by AVD, using stable ADB serials for selection."""
    options = recording_options(options)
    scope = options['scope']
    if scope == 'selected':
        selected = set(options['selectedSerials'])
        if selected - {serial for serial, _ in targets.values()}:
            raise ValueError('Um celular escolhido não está mais cadastrado. Revise os participantes.')
        targets = {name: pair for name, pair in targets.items() if pair[0] in selected}
    elif scope == 'online':
        targets = {name: pair for name, pair in targets.items() if status(pair[0]) == 'online'}
    if not targets:
        raise ValueError('Nenhum celular participante. Escolha os aparelhos antes de iniciar.')
    return dict(targets)
