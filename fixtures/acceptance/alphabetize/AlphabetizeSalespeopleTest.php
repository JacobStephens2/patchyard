<?php

declare(strict_types=1);

use PHPUnit\Framework\TestCase;

final class AlphabetizeSalespeopleTest extends TestCase
{
    public function testBothSalespersonQueriesUseFirstThenLastNameOrder(): void
    {
        $root = dirname(__DIR__, 2);
        $common = file_get_contents($root . '/mfieldbook/common_functions.php');
        $assign = file_get_contents($root . '/mfieldbook/leads/assign.php');

        self::assertIsString($common);
        self::assertIsString($assign);
        self::assertMatchesRegularExpression(
            '/function get_salespeople_usernames\(\): object \{.*?'
                . "AND username != .*?DEV_TWO_USERNAME.*?ORDER BY firstName ASC, lastName ASC.*?\\n\\s*\\\"\\);/s",
            $common,
        );
        self::assertMatchesRegularExpression(
            "/SELECT userID, firstName, lastName\\s+FROM tblUser\\s+"
                . "WHERE employeePositions LIKE '%sales%'\\s+AND userStatus = 1\\s+"
                . "ORDER BY firstName ASC, lastName ASC/s",
            $assign,
        );
    }
}
