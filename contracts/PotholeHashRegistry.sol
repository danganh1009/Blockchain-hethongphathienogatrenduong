// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PotholeHashRegistry {
    mapping(bytes32 => uint256) private _storedAt;

    event HashStored(bytes32 indexed dataHash, string imageFile, uint256 storedAt);

    function storeHash(bytes32 dataHash, string calldata imageFile) external {
        require(_storedAt[dataHash] == 0, "Hash already stored");
        _storedAt[dataHash] = block.timestamp;
        emit HashStored(dataHash, imageFile, block.timestamp);
    }

    function hasHash(bytes32 dataHash) external view returns (bool) {
        return _storedAt[dataHash] != 0;
    }
}
