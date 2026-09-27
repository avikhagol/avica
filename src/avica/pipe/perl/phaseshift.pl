#!/usr/bin/perl
use strict;
use warnings;
use Getopt::Long;
use JSON::PP;

$SIG{INT} = sub {
    print "\nCaught SIGINT! Exiting gracefully...\n";
    exit(1);
};


my $reset = 0;
my @vis;
my @outvis;
my @target;
my @c;

GetOptions(
    "reset"   => \$reset,
    "vis=s@"  => \@vis,
    "outvis=s@" => \@outvis,
    "target=s@" => \@target,
    "c=s@"      => \@c,
) or die "Invalid options passed to $0\n";

my $splitinms = '/data/avi/bin/splitinms';
my $phaseshiftpy = '/data/avi/bin/phaseshift.py';
my $virtualconcat = '/data/avi/bin/virtualconcat.py';
my $casapy311 = '/data/avi/env/casapy311/bin/python3';
my $avica = '/data/avi/env/casapy311/bin/avica';

my $vis_shifted        = $outvis[0];
my $vis_target         = $vis[0]; $vis_target         =~ s/\.ms/_target.ms.tmp_splitted/;
my $vis_target_shifted = $vis[0]; $vis_target_shifted =~ s/\.ms/_target_shifted.ms.tmp_splitted/;
my $vis_oth            = $vis[0]; $vis_oth            =~ s/\.ms/_oth.ms.tmp_splitted/;

# ANSI colors
my $cys = "\033[36m";
my $cye = "\033[0m";

# # ---------------------------------- Deactivate any active environment
# system("deactivate");

# ---------------------------------- Find Sources
print "$cys\n## --------- Finding Sources : (@vis)\n$cye";
my $cmd_find_sources = "$casapy311 $splitinms --json-out sources.json --target @target @vis";
print "$cmd_find_sources\n";
system($cmd_find_sources) == 0 or die "Failed to run splitinms for source finding\n";

# ---------------------------------- Read JSON
sub get_json {
    open my $fh, '<', 'sources.json' or die "Cannot open sources.json: $!";
    local $/; # slurp mode
    my $json_text = <$fh>;
    close $fh;

    my $data = JSON::PP->new->decode($json_text);
    return $data;
}

my $data = get_json();

# ---------------------------------- Split non-target sources
print "$cys\n## --------- Splitting : non-target sources ($vis_oth)\n$cye";
my $cmd_split_nontarget = "$splitinms @vis $vis_oth --fields $data->{oth} --datacolumn data --mpi 5";
print "$cmd_split_nontarget\n";
system("rm -rf $vis_oth");
system("$cmd_split_nontarget") == 0 or die "Failed to run $cmd_split_nontarget";

# ---------------------------------- Split target source
print "$cys\n## --------- Splitting : $data->{target} ($vis_target)\n$cye";
my $cmd_split_target = "$splitinms @vis $vis_target --fields $data->{target} --datacolumn data --mpi 5";
print "$cmd_split_target\n";
system("rm -rf $vis_target");
system("$cmd_split_target") == 0 or die "Failed to run $cmd_split_target";

# ---------------------------------- Phaseshift
my $c_str = join(',', @c);
print "$cys\n## --------- Phaseshift : $data->{target} ($vis_target_shifted)\n$cye";
my $cmd_phaseshift = "$phaseshiftpy $vis_target $vis_target_shifted -c '$c_str' --mpi 5";
print "$cmd_phaseshift\n";
system("rm -rf $vis_target_shifted");
system("$cmd_phaseshift") == 0 or die "Failed to run $cmd_phaseshift";

# ---------------------------------- Concatenate
# my $c_str = join(',', @c);
print "$cys\n## --------- Concat : $vis_shifted\n$cye";
my $cmd_concat = "$virtualconcat --concatvis $vis_shifted $vis_target_shifted $vis_oth --py";
print "$cmd_concat\n\n";
system("rm -rf $vis_shifted");
system("$cmd_concat") == 0 or die "Failed to run $cmd_concat";

# ----------------------------------- Fixing Duplicates
print "$cys\n## --------- Fixing duplicates : $vis_shifted\n$cye";
my $cmd_fix = "$avica @vis $vis_shifted --fix-dupl --modify";
print "$cmd_fix\n\n";
system("$cmd_fix") == 0 or die "Failed to run $cmd_concat";
