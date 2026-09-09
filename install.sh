#!/usr/bin/env bash
# Install AVICA and reuse an existing rPICARD installation whenever possible.
set -euo pipefail

main() {
    local install_dir="${AVICA_INSTALL_DIR:-$HOME/.local/share/avica-stack}"
    local avica_source_dir="${AVICA_SOURCE_DIR:-}"
    local default_casa_url='ftp://ftp.mpifr-bonn.mpg.de/outgoing/mjanssen/casa-6.7.5-18-py3.12.el8.tar.xz'
    local casa_source="${CASA_PATH:-${CASA_DIR:-${CASA_URL:-}}}"
    local casa_dir='' picard_dir='' picard_bin='' tool_bin

    if [[ ${1:-} == --help ]]; then
        printf '%s\n' 'Usage: bash install.sh' \
            'CASA_PATH: existing CASA directory or archive URL (prompted if unset).' \
            'CASA_DIR and CASA_URL are also accepted, in that order.' \
            "Default CASA archive: $default_casa_url" \
            'AVICA_INSTALL_DIR: installation directory (default: ~/.local/share/avica-stack).' \
            'AVICA_SOURCE_DIR: local AVICA source directory to install instead of the latest PyPI version.' \
            'PICARD_REF: branch/tag for a new rPICARD clone (default: master).'
        return
    fi
    [[ $# == 0 ]] || { printf 'Use bash install.sh --help for usage.\n' >&2; return 1; }

    mkdir -p "$install_dir" "$HOME/.local/bin"
    install_dir=$(realpath "$install_dir")
    if [[ -n $avica_source_dir ]]; then
        avica_source_dir=$(realpath "$avica_source_dir")
    fi
    export PATH="$HOME/.local/bin:$PATH"

    if [[ -n $avica_source_dir ]]; then
        printf '\nUsing AVICA_SOURCE_DIR instead of the latest PyPI version: %s\n' "$avica_source_dir"
    else
        printf '\nInstalling AVICA...\n'
    fi
    if ! command -v uv >/dev/null; then
        curl -fsSL https://astral.sh/uv/install.sh -o "$install_dir/uv-install.sh"
        UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$install_dir/uv-install.sh" </dev/null
    fi
    if [[ -n $avica_source_dir ]]; then
        uv tool install --python 3.10 "$avica_source_dir" </dev/null
    else
        uv tool install --python 3.10 avica </dev/null
    fi
    tool_bin=$(uv tool dir --bin)
    export PATH="$tool_bin:$PATH"

    if command -v picard >/dev/null; then
        printf '\nUsing existing rPICARD: %s\n' "$(command -v picard)"
        picard_bin=$(dirname "$(readlink -f "$(command -v picard)")")
        picard_dir=$(dirname "$picard_bin")
        # Standard rPICARD installations record their CASA bin directory here.
        if [[ -f $picard_dir/your_casapath.txt ]]; then
            casa_dir=$(< "$picard_dir/your_casapath.txt")
            casa_dir=${casa_dir%/}
            casa_dir=${casa_dir%/bin}
        fi
    else
        if [[ -z $casa_source ]]; then
            printf '\nEnter a CASA directory or archive URL.\nDefault: %s\n' "$default_casa_url"
            # Use the terminal even when install.sh is piped into bash.
            if { exec 3<>/dev/tty; } 2>/dev/null; then
                read -r -u 3 -p 'CASA location (Enter for default): ' casa_source || true
                exec 3>&-
            else
                printf 'No terminal available; using the default CASA archive.\n'
            fi
            casa_source=${casa_source:-$default_casa_url}
        fi

        case "$casa_source" in
            ftp://*|http://*|https://*)
                local archive_name=${casa_source##*/}
                local casa_name=${archive_name%.tar.xz}
                [[ $archive_name == casa-*.tar.xz ]] || { printf 'Expected a casa-*.tar.xz archive URL.\n' >&2; return 1; }
                casa_dir="$install_dir/$casa_name"
                if [[ ! -d $casa_dir ]]; then
                    printf '\nDownloading CASA: %s\n' "$casa_source"
                    curl -fL --retry 3 -C - "$casa_source" -o "$install_dir/$archive_name.part"
                    tar -xJf "$install_dir/$archive_name.part" --no-same-owner -C "$install_dir"
                    mv "$install_dir/$archive_name.part" "$install_dir/$archive_name"
                fi
                ;;
            *) casa_dir=$(realpath "$casa_source") ;;
        esac

        [[ -x $casa_dir/bin/casa && -x $casa_dir/bin/mpicasa ]] || {
            printf 'CASA must contain bin/casa and bin/mpicasa: %s\n' "$casa_dir" >&2
            return 1
        }
        printf '\nSaving CASA path in AVICA global configuration...\n'
        "$tool_bin/avica" pipe config --global "casadir=$casa_dir/" </dev/null

        picard_dir="$install_dir/picard"
        picard_bin="$picard_dir/picard"
        printf '\nSetting up rPICARD...\n'
        if [[ ! -d $picard_dir ]]; then
            git clone --depth 1 --branch "${PICARD_REF:-master}" \
                https://bitbucket.org/M_Janssen/picard.git "$picard_dir" </dev/null
        fi
        python3 "$picard_dir/setup.py" -a -p "$casa_dir" </dev/null

        uv tool install --python 3.10 --with python-pgplot==1.6.1 \
            'git+https://github.com/haavee/jiveplot' </dev/null
        mkdir -p "$HOME/.casa/data"
        rsync -az --partial rsync://casa-rsync.nrao.edu/casa-data "$HOME/.casa/data/" </dev/null
    fi

    # Preserve existing AVICA settings while linking a known rPICARD/CASA setup.
    if [[ -n $casa_dir && -d $picard_dir/input_template ]]; then
        local -a config_args=(pipe config --default)
        mkdir -p "$HOME/.avica"
        if [[ -f $HOME/.avica/avica.inp ]]; then
            cp --backup=numbered -p "$HOME/.avica/avica.inp" "$HOME/.avica/avica.inp.before-install"
            config_args+=(--inpfile "$HOME/.avica/avica.inp")
        fi
        "$tool_bin/avica" "${config_args[@]}" "casadir=$casa_dir/" \
            "picard_input_template=$picard_dir/input_template/" </dev/null
    fi

    # Save the paths for this shell and future Bash sessions.
    {
        # shellcheck disable=SC2016
        printf 'export PATH=%q:"$PATH"\n' "$tool_bin:$picard_bin"
        # shellcheck disable=SC2016
        printf 'export PYTHONPATH=%q${PYTHONPATH:+:"$PYTHONPATH"}\n' "$picard_bin"
    } > "$install_dir/env.sh"
    local source_line
    printf -v source_line '. %q' "$install_dir/env.sh"
    if ! grep -Fqx "$source_line" "$HOME/.bashrc" 2>/dev/null; then
        printf '\n# AVICA environment\n%s\n' "$source_line" >> "$HOME/.bashrc"
    fi
    printf '\nInstallation finished. Run:\n  source %q\n  avica --help\n' "$install_dir/env.sh"
}

main "$@"
