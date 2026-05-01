#!/usr/bin/perl
use strict;
use warnings;


use Scalar::Util qw(looks_like_number);
use JSON::PP;
# use JSON::XS;

my $json_text = do {
    local $/;
    <STDIN>
};

print STDERR "DEBUG raw stdin: '$json_text'\n";
my $json = JSON::PP->new->ascii->pretty->allow_nonref;
my $perl_scalar = $json->decode( $json_text );
my $pretty_printed_json_text = $json->encode( $perl_scalar );

my @cmd_list_json = @{ $perl_scalar->{"tasks_list"} };
my $saved_stdout;

foreach my $item (@cmd_list_json){
    
    my $cmd_json = $item->{"cmd"};
    my $casadir = $cmd_json->{"casadir"};
    my $logfile = $cmd_json->{"logfile"};
    my $errf = $cmd_json->{"errf"};
    my $task_casa = $cmd_json->{"task_casa"};
    my $args = $cmd_json->{"args"};
    my $args_type = $cmd_json->{"args_type"};
    my $mpi = $cmd_json->{"mpi_cores"};

    my @run_cmd_list;

    if ($mpi != 0) {
        push(@run_cmd_list, $casadir . "bin/mpicasa", "--oversubscribe", "-n", $mpi);
    }

    my @task_cmd_list;

    my $casa_args = "";
    $casa_args .= $task_casa;




    foreach my $key (keys %$args) {
        my $value = $args->{$key};
        my $type = $args_type->{$key};
        my $formatted_val = "";
        if ($type =~ /^List\[(.*)\]/) {
            my $inner_type = $1;
            my @processed = map { parse_by_type($_, $inner_type) } @$value;
            $formatted_val = "[" . join(",", @processed) . "]";
        }
        else {
            $formatted_val = parse_by_type($value, $type);
        }
        
        
        push(@task_cmd_list, "$key=$formatted_val");
    }
    print STDERR "casa_args: $casa_args\n";
    print STDERR "run_cmd_list: " . join(" ", @run_cmd_list) . "\n";
    
    sub parse_by_type{
        my ($v, $t) = @_;
        if ($t eq 'str') {
            return "'$v'";
        }
        elsif ($t eq 'bool') {
            return $v ? "True" : "False";
        }
        elsif ($t eq 'int' || $t eq 'float') {
            return $v;
        }
        else {
            return $v;
        }
        
    }

    $casa_args .= "(" . join(",", @task_cmd_list) . ")";

    push(@run_cmd_list, $casadir . "bin/casa", "--agg", "--nogui", "--logfile", $logfile, "-c", $casa_args );
    # print $casa_args . "\n";

    open(my $casa_stdout, ">&STDOUT") or die "error saving STDOUT: $!";
    open(STDOUT, ">&STDERR")          or die "error redirecting STDOUT: $!";
    STDOUT->autoflush(1);

    my $saved_stderr;
    if ($errf) {
        open($saved_stderr, ">&STDERR")       or die "error saving STDERR: $!";
        open(STDERR, ">", $errf)              or die "error opening errf: $!";
        STDERR->autoflush(1);
    }


    my $exit_code = system(@run_cmd_list);

    open(STDOUT, ">&", $casa_stdout)  or die "error restoring STDOUT: $!";
    close($casa_stdout);

    if ($exit_code != 0) {
        die "Command ended with exit code: $exit_code";
    }

    if ($errf && $saved_stderr) {
    open(STDERR, ">&", $saved_stderr) or die "error restoring STDERR: $!";
    close($saved_stderr);
}

}

# my %result = (success => 1, message => "all tasks completed");
# print encode_json(\%result) . "\n";