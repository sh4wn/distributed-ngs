import os
import asyncio
import json
import logging
import uuid

from digs.common.utils import connect_to_random_central_server
from digs.common.actions import PerformBWAJob, LocateData, GetDataChunk
from digs.messaging.protocol import DigsProtocolParser
from digs.messaging.persistent import PersistentProtocol

persistent_parser = DigsProtocolParser()
logger = logging.getLogger(__name__)


class WorkerProtocol(PersistentProtocol):
    @property
    def parser(self):
        return persistent_parser


@persistent_parser.register_handler(PerformBWAJob)
async def perform_bwa(protocol, action):
    logger.debug("Accepting job: %s", action)
    # Retrieve chunk from data node
    # But first find the corresponding data nodes for the reads data and the
    # reference genome
    reader, writer = await connect_to_random_central_server()

    writer.send(str(
        LocateData(search_by='file_id', term=action['reads_data'])
    ))
    await writer.drain()

    data = await reader.readline()
    logger.debug("Received data: %s", data)
    parts = data.strip().split(maxsplit=1)

    assert parts[0] == 'locate_data_result'
    reads_datanode = json.loads(parts[1])
    logger.info("Reads data node: %s", reads_datanode)

    writer.send(str(
        LocateData(search_by='file_id', term=action['reference_genome'])
    ))
    await writer.drain()

    data = await reader.readline()
    logger.debug("Received data: %s", data)
    parts = data.strip().split(maxsplit=1)

    assert parts[0] == 'locate_data_result'
    reference_genome_datanode = json.loads(parts[1])
    logger.info("Reference genome node: %s", reference_genome_datanode)

    writer.close()

    # Create random job id, and create a new directory
    job_id = uuid.uuid4()
    path = os.path.join("jobs", str(job_id))
    os.makedirs(path, exist_ok=True)

    # Download reads data chunk
    reader, writer = await asyncio.open_connection(reads_datanode['ip'], 5001)
    writer.write(str(
        GetDataChunk(
            file_path=reads_datanode['path'],
            chunk_start=action['chunk_start'],
            chunk_end=action['chunk_end']
        )
    ))

    size = action['chunk_end'] - action['chunk_start']
    read_bytes = 0

    with open(os.path.join(path, "reads.fastq"), "wb") as f:
        while read_bytes < size:
            data = await reader.read(4096)
            read_bytes += len(data)

            if not data:
                raise IOError("Got EOF, but read only {} bytes of a chunk "
                              "with size {}".format(read_bytes, size))

            f.write(data)

    writer.close()

    # Download reference genome
    reader, writer = await asyncio.open_connection(
        reference_genome_datanode['ip'], 5001)

    writer.write(str(
        GetDataChunk(
            file_path=reference_genome_datanode['path'],
            chunk_start=0,
            chunk_end=-1
        )
    ))

    with open(os.path.join(path, "reference.fasta"), "wb") as f:
        while True:
            data = await reader.read(4096)

            if not data:
                break

            f.write(data)

    writer.close()
