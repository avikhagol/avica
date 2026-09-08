#!/usr/bin/env bash
# Install AVICA and the rPICARD/CASA stack from dockerfiles/default/Dockerfile.
# Normal runs only check system packages. Use sudo to install apt packages first.
set -Eeuo pipefail

usage() {
    cat <<'HELP'
Usage: bash install.sh [options]

Install AVICA, rPICARD, its matching CASA build, jiveplot, and CASA data.
Requires x86-64 Ubuntu 22.04+/Debian 12+ (or a compatible derivative),
an internet connection, and several GB of free disk space.

By default, only check system packages and warn about missing dependencies.
To install system packages too, run: sudo bash install.sh [options]
The sudo run then installs AVICA and the pipeline as the invoking user.

Options:
  --prefix DIR       Pipeline directory (default: ~/.local/share/avica-stack)
  --casa-dir DIR     Reuse an existing matching CASA directory containing bin/casa
  --avica-only       Install only AVICA and its dependencies
  --skip-apt         Only check system packages, even when running with sudo
  --skip-casa-data   Skip CASA reference data synchronization
  --no-shell        Do not add the environment file to ~/.bashrc
  -h, --help         Show this help without changing anything

Environment overrides:
  AVICA_VERSION     PyPI version to install (default: latest available)
  PICARD_REF        rPICARD branch or tag for a fresh clone (default: master)
  CASA_URL          HTTPS archive URL (default: read from rPICARD's README)

Existing rPICARD clones and CASA directories are reused, not updated.
Rerun with a new --prefix to install a different rPICARD version.
HELP
}

log() { printf '\n==> %s\n' "$*"; }
warn() { printf '\nWarning: %s\n' "$*" >&2; }
die() { printf '\nError: %s\n' "$*" >&2; exit 1; }

download() {
    curl --fail --location --show-error --retry 3 --connect-timeout 30 \
        --proto '=https' --proto-redir '=https' "$@"
}

main() {
    local prefix="${HOME:?HOME must be set}/.local/share/avica-stack"
    local casa_dir='' avica_only=0 skip_apt=0 skip_data=0 no_shell=0
    local -a original_args=("$@")
    local warnings=0 script_path=''
    local arg
    while (( $# )); do
        case "$1" in
            --prefix|--casa-dir)
                arg=$1
                [[ $# -ge 2 && -n $2 && $2 != --* ]] || die "$arg requires a directory."
                if [[ $arg == --prefix ]]; then prefix=$2; else casa_dir=$2; fi
                shift 2 ;;
            --avica-only) avica_only=1; shift ;;
            --skip-apt) skip_apt=1; shift ;;
            --skip-casa-data) skip_data=1; shift ;;
            --no-shell) no_shell=1; shift ;;
            -h|--help) usage; return ;;
            *) die "Unknown option: $1 (see --help)." ;;
        esac
    done

    [[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] ||
        die 'This installer requires x86-64 Linux. Use Docker on other platforms.'
    if (( EUID == 0 )); then
        [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] ||
            die 'Use sudo bash install.sh from a regular user account so AVICA is installed for that user.'
        local invoking_uid
        invoking_uid=$(id -u -- "$SUDO_USER") || die 'Cannot identify the invoking user.'
        [[ $invoking_uid != 0 ]] || die 'The invoking user must not be root.'
        [[ -f ${BASH_SOURCE[0]:-} ]] || die 'For sudo installation, download install.sh to a file first.'
        script_path=$(realpath "${BASH_SOURCE[0]}")
    fi
    [[ -r /etc/os-release ]] || die 'Cannot identify this Linux distribution.'
    # shellcheck disable=SC1091
    . /etc/os-release
    case " ${ID:-} ${ID_LIKE:-} " in
        *ubuntu*|*debian*|*linuxmint*) ;;
        *) die 'This installer requires Ubuntu/Debian or a compatible derivative.' ;;
    esac
    # Upstream rPICARD builds unquoted shell commands using these paths.
    [[ $prefix =~ ^/[a-zA-Z0-9_./+-]+$ && $prefix != / ]] ||
        die '--prefix must be an absolute path without spaces or shell metacharacters.'
    if [[ -n $casa_dir ]]; then
        [[ $casa_dir =~ ^/[a-zA-Z0-9_./+-]+$ ]] || die '--casa-dir must be an absolute path without spaces or shell metacharacters.'
        [[ -x $casa_dir/bin/casa && -x $casa_dir/bin/mpicasa ]] || die '--casa-dir must contain executable bin/casa and bin/mpicasa.'
        casa_dir=$(realpath "$casa_dir")
        [[ $casa_dir =~ ^/[a-zA-Z0-9_./+-]+$ ]] || die 'The resolved --casa-dir path is unsupported.'
    fi

    local -a packages=(ca-certificates curl git build-essential cmake pkg-config
        python3 python3-tk)
    if (( ! avica_only )); then
        packages+=(xz-utils rsync perl openssh-client locales
            python3-matplotlib python3-six
            libfreetype6 libsm6 libxi6 libxrender1 libxrandr2 libxfixes3
            libxcursor1 libxinerama1 libfontconfig1 libxslt1.1
            libgl1 libglu1-mesa libx11-6 libxcb-xinerama0 libxkbcommon-x11-0
            libgfortran5 libnsl2 xauth xvfb dbus-x11)
    fi
    if (( EUID == 0 )); then
        if (( ! skip_apt )); then
            log 'Installing system dependencies as root'
            if ! apt-get update </dev/null; then
                warn 'apt-get update failed; trying the available package lists.'
            fi
            if ! env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}" </dev/null; then
                warn 'System package installation failed. Continuing as the invoking user and checking missing dependencies.'
            fi
        fi
        log "Continuing the user installation as $SUDO_USER"
        # sudo supplies the user's home; never install Python tools into root's home.
        exec sudo -H -u "$SUDO_USER" -- env \
            AVICA_VERSION="${AVICA_VERSION:-}" PICARD_REF="${PICARD_REF:-master}" CASA_URL="${CASA_URL:-}" \
            bash "$script_path" --skip-apt "${original_args[@]}"
    fi

    log 'Checking system dependencies (no apt commands will be run)'
    local package
    local -a missing_packages=()
    if command -v dpkg-query >/dev/null; then
        for package in "${packages[@]}"; do
            if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null) != 'install ok installed' ]]; then
                missing_packages+=("$package")
            fi
        done
        if (( ${#missing_packages[@]} )); then
            warnings=1
            warn 'These system packages are not reported as installed:'
            printf '  %s\n' "${missing_packages[@]}" >&2
            warn 'Continuing without apt. Missing dependencies may cause errors when executing AVICA, CASA, or plotting tools.'
            printf '\nAsk an administrator to install the missing packages:\n  sudo apt-get install --no-install-recommends' >&2
            printf ' %q' "${missing_packages[@]}" >&2
            printf '\n' >&2
        else
            log 'All listed system packages are installed'
        fi
    else
        warnings=1
        warn 'dpkg-query is unavailable; cannot verify system packages. Continuing, but AVICA/CASA may encounter missing dependencies.'
    fi

    export PATH="$HOME/.local/bin:$PATH"
    local cmd
    local -a installer_commands=()
    command -v uv >/dev/null || installer_commands+=(curl)
    if (( ! avica_only )); then
        installer_commands+=(git python3)
        [[ -n $casa_dir ]] || installer_commands+=(curl tar xz)
        if (( ! skip_data )) && ! command -v rsync >/dev/null; then
            warnings=1
            skip_data=1
            warn 'rsync is unavailable; skipping CASA reference data. Install rsync and synchronize the data before processing observations.'
        fi
    fi
    for cmd in "${installer_commands[@]}"; do
        command -v "$cmd" >/dev/null || die "Missing installer command: $cmd. It is needed to perform this installation; ask an administrator to provide it. No apt commands were run."
    done

    mkdir -p "$prefix" "$HOME/.local/bin"
    prefix=$(realpath "$prefix")
    [[ $prefix =~ ^/[a-zA-Z0-9_./+-]+$ && $prefix != / ]] || die 'The resolved --prefix path is unsupported.'
    local scratch
    scratch=$(mktemp -d "$prefix/.install.XXXXXXXX")
    # This directory is created by this run; keep downloaded CASA archives separately.
    trap 'rm -rf -- "$scratch"' EXIT
    trap 'printf "\nInstallation failed at line %s. Fix the error above and rerun.\n" "$LINENO" >&2' ERR
    if ! command -v uv >/dev/null; then
        log 'Installing uv'
        download https://astral.sh/uv/install.sh -o "$scratch/uv-install.sh"
        env UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$scratch/uv-install.sh" </dev/null
    fi

    local avica_spec=avica tool_bin picard_dir="$prefix/picard"
    [[ -z ${AVICA_VERSION:-} ]] || avica_spec="avica==$AVICA_VERSION"
    log 'Installing AVICA with an isolated Python 3.10 environment'
    uv tool install --python 3.10 --managed-python "$avica_spec" </dev/null
    tool_bin=$(uv tool dir --bin)
    export PATH="$tool_bin:$PATH"
    if ! "$tool_bin/avica" --help > "$scratch/avica-check.log" 2>&1; then
        warnings=1
        warn 'AVICA was installed but its startup check failed. It may need missing system dependencies before it can run:'
        cat "$scratch/avica-check.log" >&2
    fi
    # Preserve a previous full environment if a later step fails on a rerun.
    if [[ ! -f $prefix/env.sh ]]; then
        # shellcheck disable=SC2016
        printf 'export PATH=%q:"$PATH"\n' "$tool_bin" > "$prefix/env.sh"
    fi

    if (( ! avica_only )); then
        log 'Preparing rPICARD'
        if [[ -e $picard_dir ]]; then
            [[ -d $picard_dir/.git && -f $picard_dir/setup.py && -f $picard_dir/README.md ]] ||
                die "$picard_dir already exists but is not an rPICARD clone. Choose another --prefix."
            log "Reusing $picard_dir (including any local changes)"
        else
            git clone --single-branch --depth 1 --branch "${PICARD_REF:-master}" \
                https://bitbucket.org/M_Janssen/picard.git "$scratch/picard" </dev/null
            mv "$scratch/picard" "$picard_dir"
        fi

        if [[ -z $casa_dir ]]; then
            local casa_url=${CASA_URL:-} archive_name casa_name archive
            if [[ -z $casa_url ]]; then
                # Read the wget command as text; never execute README content.
                casa_url=$(awk '/\$ wget / {for (i=1;i<=NF;i++) if ($i ~ /^(https?|ftp):\/\/.*casa-.*\.tar\.xz$/) {print $i; exit}}' "$picard_dir/README.md")
            fi
            # The rPICARD FTP archive is also served over HTTPS on the same host.
            casa_url=${casa_url/#ftp:\/\/ftp.mpifr-bonn.mpg.de\//https:\/\/ftp.mpifr-bonn.mpg.de\/}
            [[ $casa_url == https://* ]] || die 'No HTTPS CASA archive found. Set CASA_URL to the matching archive URL.'
            archive_name=${casa_url##*/}
            [[ $archive_name =~ ^casa-[a-zA-Z0-9_.+-]+\.tar\.xz$ ]] || die "Unrecognized CASA archive name: $archive_name"
            casa_name=${archive_name%.tar.xz}
            casa_dir="$prefix/$casa_name"
            if [[ ! -e $casa_dir ]]; then
                mkdir -p "$prefix/downloads"
                archive="$prefix/downloads/$archive_name"
                if [[ ! -f $archive ]]; then
                    log "Downloading $casa_url (interrupted downloads can be resumed)"
                    download --continue-at - "$casa_url" -o "$archive.part"
                    mv "$archive.part" "$archive"
                fi
                log 'Extracting CASA'
                tar -tJf "$archive" > "$scratch/archive-members"
                awk -v root="$casa_name" '
                    $0 != root && index($0, root "/") != 1 {bad=1}
                    /(^|\/)\.\.(\/|$)/ {bad=1}
                    END {exit bad || NR == 0}
                ' "$scratch/archive-members" || die "Unexpected archive layout in $archive."
                tar -xJf "$archive" --no-same-owner -C "$scratch"
                [[ -x $scratch/$casa_name/bin/casa && -x $scratch/$casa_name/bin/mpicasa ]] ||
                    die 'The extracted CASA archive does not contain bin/casa and bin/mpicasa.'
                mv "$scratch/$casa_name" "$casa_dir"
            fi
        fi
        [[ -x $casa_dir/bin/casa && -x $casa_dir/bin/mpicasa ]] ||
            die "Incomplete CASA installation at $casa_dir. Choose a new --prefix or --casa-dir."

        log 'Installing jiveplot and python-pgplot'
        uv tool install --python 3.10 --managed-python --with python-pgplot==1.6.1 \
            'git+https://github.com/haavee/jiveplot' </dev/null
        [[ -x $tool_bin/jplotter && -x $tool_bin/standardplots ]] || die 'jiveplot executables were not installed.'

        log 'Linking rPICARD to CASA'
        python3 "$picard_dir/setup.py" -a -p "$casa_dir" </dev/null
        [[ -s $picard_dir/your_casapath.txt && -x $picard_dir/picard/picard ]] || die 'rPICARD setup did not complete.'
        mkdir -p "$HOME/.casa/data" "$HOME/.cache/matplotlib" "$HOME/.avica"
        if (( ! skip_data )); then
            log 'Synchronizing CASA reference data (this can take a while)'
            rsync -az --partial --timeout=120 rsync://casa-rsync.nrao.edu/casa-data "$HOME/.casa/data/" </dev/null
        fi

        local -a config_args=(pipe config --default)
        if [[ -f $HOME/.avica/avica.inp ]]; then
            cp --backup=numbered -p "$HOME/.avica/avica.inp" "$HOME/.avica/avica.inp.before-install"
            config_args+=(--inpfile "$HOME/.avica/avica.inp")
        fi
        if ! "$tool_bin/avica" "${config_args[@]}" "casadir=$casa_dir/" \
            "picard_input_template=$picard_dir/input_template/" </dev/null; then
            warnings=1
            warn 'Could not save AVICA pipeline settings. Resolve its runtime errors and rerun this installer to finish configuration.'
        fi
        {
            # Expand PATH/PYTHONPATH when sourcing the generated file.
            # shellcheck disable=SC2016
            printf 'export PATH=%q:"$PATH"\n' "$tool_bin:$picard_dir/picard"
            # shellcheck disable=SC2016
            printf 'export PYTHONPATH=%q${PYTHONPATH:+:"$PYTHONPATH"}\n' "$picard_dir/picard"
        } > "$prefix/env.sh"
    fi

    if (( ! no_shell )); then
        local source_line
        printf -v source_line '. %q' "$prefix/env.sh"
        if ! grep -Fqx "$source_line" "$HOME/.bashrc" 2>/dev/null; then
            printf '\n# AVICA environment\n%s\n' "$source_line" >> "$HOME/.bashrc"
        fi
    fi
    if (( warnings )); then
        warn 'Installation finished with dependency or runtime warnings. AVICA or pipeline features may fail until the issues above are resolved.'
    fi
    log 'Installation finished. Enable the commands in your current Bash session:'
    printf '  source %q\n  avica --help\n' "$prefix/env.sh"
    if (( ! avica_only )); then
        printf '\nCASA: %s\nrPICARD: %s\n' "$casa_dir" "$picard_dir"
        (( ! skip_data )) || printf '\nCASA data was skipped; synchronize it before processing observations.\n'
    fi
    # Cleanup before local variables go out of scope.
    rm -rf -- "$scratch"
    trap - EXIT ERR
}

# Keep the invocation last so piping the script into bash reads the functions first.
main "$@"
