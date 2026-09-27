#
from traceback import print_exc
MPICLIENT = None


def get_mpi_client():
    """Returns the existing client or starts a new one if needed."""
    from casampi.MPICommandClient import MPIEnvironment
    global MPICLIENT
    if MPIEnvironment.is_mpi_enabled:
        if MPICLIENT is None:
            start_mpi()
    return MPICLIENT

def start_mpi():
    from casampi.MPICommandClient import MPICommandClient
    global MPICLIENT
    try:
        MPICLIENT = MPICommandClient()
        MPICLIENT.start_services()
        MPICLIENT.set_log_mode('redirect')
        MPICLIENT.set_log_level('INFO4')
    except Exception as e:
        print_exc()
        raise
    return MPICLIENT


# mpiclient.py
# from casampi.MPICommandClient import MPICommandClient
# from mpi4py import MPI

# MPICLIENT = None

# def get_mpi_client():
#     start_mpi()
#     return MPICLIENT

# def start_mpi():
#     global MPICLIENT
#     if MPICLIENT is not None:
#         return
#     # Use mpi4py directly — MPIEnvironment.is_mpi_enabled is unreliable
#     # with a foreign Python interpreter
#     rank = MPI.COMM_WORLD.Get_rank()
#     size = MPI.COMM_WORLD.Get_size()
#     if size > 1 and rank == 0:
#         try:
#             MPICLIENT = MPICommandClient()
#             MPICLIENT.start_services()
#         except RuntimeError:
#             MPICLIENT = None
#     else:
#         MPICLIENT = None
